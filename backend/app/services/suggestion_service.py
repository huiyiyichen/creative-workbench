"""AI 修改建议（设计文档 5.4、12 节）：模型返回补丁操作，按处接受或拒绝。

操作：replace_paragraph(id, text) / insert_after(id, text) / delete_paragraph(id) /
update_shot(index, field, value) / insert_shot(after, shot) / delete_shot(index) / move_shot(from, to)。
服务端校验 id 存在、字段与长度边界（沿用 StudioShot / StudioDraft 上限）、操作数 ≤50。
apply 时若 base_token 与当前不一致，只应用目标段落 / 分镜未被改过的操作，其余标为冲突返回。
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundError, ValidationError
from app.models.project import ProjectSuggestion
from app.schemas.studio import StudioDraft, StudioShot
from app.services import project_service as ps

logger = logging.getLogger(__name__)

MAX_OPS = 50
PARA_MAX = 8000
SHOT_FIELDS = {"seconds", "beat", "visual", "camera", "audio", "transition", "caption", "prompt"}
QUICK = {
    "colloquial": "改得更口语，像对朋友讲",
    "formal": "改得更正式、书面",
    "compress": "压缩到 {n} 字左右，保留关键信息",
    "new_opening": "换一个更抓人的开头",
    "add_example": "加一个具体例子",
    "template": "按内容模板的结构重排",
    "cite": "为缺少出处的事实补充来源依据（只用已给来源）",
}


class SuggestionError(ValidationError):
    pass


# ── 校验 ─────────────────────────────────────────────────────────────


def _text(value: Any, limit: int = PARA_MAX) -> str:
    text = str(value or "").strip()
    if not text:
        raise SuggestionError("建议里有空文本")
    return text[:limit]


def validate_ops(raw_ops: Any, draft: dict, scope: dict) -> list[dict]:
    """把模型返回的操作规整成带 op_id 的合法操作；不合法的直接丢弃。"""
    if not isinstance(raw_ops, list):
        raise SuggestionError("建议不是操作列表")
    paras = ps.paragraphs_with_ids(draft.get("body", ""))
    pids = {p["id"] for p in paras}
    n_shots = len(draft.get("shots") or [])
    allowed_p = set(scope.get("ids") or []) if scope.get("type") == "paragraphs" else None
    allowed_s = set(scope.get("indexes") or []) if scope.get("type") == "shots" else None
    if scope.get("type") == "paragraphs":
        allowed_s = set()  # 只改选中段落时不动分镜
    if scope.get("type") == "shots":
        allowed_p = set()
    ops: list[dict] = []
    for raw in raw_ops[: MAX_OPS * 2]:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("op") or raw.get("type")
        try:
            if kind in {"replace_paragraph", "insert_after", "delete_paragraph"}:
                pid = str(raw.get("id") or "")
                if pid not in pids or (allowed_p is not None and pid not in allowed_p):
                    continue
                op = {"op": kind, "id": pid}
                if kind != "delete_paragraph":
                    op["text"] = _text(raw.get("text"))
            elif kind == "update_shot":
                idx, field = int(raw.get("index")), str(raw.get("field") or "")
                if not 0 <= idx < n_shots or field not in SHOT_FIELDS:
                    continue
                if allowed_s is not None and idx not in allowed_s:
                    continue
                value: Any = raw.get("value")
                if field == "seconds":
                    value = min(600.0, max(0.1, float(value)))
                else:
                    StudioShot.model_validate({"seconds": 1, field: str(value or "")})
                    value = str(value or "")
                op = {"op": kind, "index": idx, "field": field, "value": value}
            elif kind == "insert_shot":
                after = int(raw.get("after", -1))
                if not -1 <= after < n_shots or (allowed_s is not None and after not in allowed_s):
                    continue
                shot = StudioShot.model_validate(
                    {**(raw.get("shot") or {}), "seconds": (raw.get("shot") or {}).get("seconds") or 3}
                )
                op = {"op": kind, "after": after, "shot": shot.model_dump(mode="json")}
            elif kind == "delete_shot":
                idx = int(raw.get("index"))
                if not 0 <= idx < n_shots or (allowed_s is not None and idx not in allowed_s):
                    continue
                op = {"op": kind, "index": idx}
            elif kind == "move_shot":
                src, dst = int(raw.get("from")), int(raw.get("to"))
                if not (0 <= src < n_shots and 0 <= dst < n_shots) or src == dst or allowed_s is not None:
                    continue
                op = {"op": kind, "from": src, "to": dst}
            else:
                continue
        except (TypeError, ValueError, SuggestionError):
            continue
        if raw.get("reason"):
            op["reason"] = str(raw["reason"])[:300]
        op["op_id"] = f"o{len(ops) + 1}"
        ops.append(op)
        if len(ops) >= MAX_OPS:
            break
    return ops


# ── 应用 ─────────────────────────────────────────────────────────────


def apply_ops(draft: dict, ops: list[dict], base_draft: dict | None = None) -> tuple[dict, list[str], list[str]]:
    """把操作作用到 draft 上。base_draft 给出时（token 已变），目标已被改动的操作记为冲突。

    返回 (新 draft, 已应用 op_id, 冲突 op_id)。段落按 id 定位（id 由内容哈希得到，段落没改 id 就不变）；
    分镜按序号定位，冲突判断看该序号的分镜是否与 base 时一致。
    """
    result = deepcopy(draft)
    paras = ps.paragraphs_with_ids(result.get("body", ""))
    shots: list[dict | None] = list(deepcopy(result.get("shots") or []))
    base_shots = (base_draft or {}).get("shots") or []
    applied: list[str] = []
    conflicts: list[str] = []
    by_id = {p["id"]: p for p in paras}
    inserts: dict[str, list[str]] = {}
    shot_inserts: dict[int, list[dict]] = {}
    moves: list[tuple[int, int]] = []

    def shot_changed(idx: int) -> bool:
        if base_draft is None:
            return False
        return idx >= len(base_shots) or idx >= len(draft.get("shots") or []) or base_shots[idx] != draft["shots"][idx]

    for op in ops:
        kind = op["op"]
        if kind in {"replace_paragraph", "insert_after", "delete_paragraph"}:
            p = by_id.get(op["id"])
            if p is None or p.get("_deleted"):
                conflicts.append(op["op_id"])
                continue
            if kind == "replace_paragraph":
                p["text"] = op["text"]
            elif kind == "delete_paragraph":
                p["_deleted"] = True
            else:
                inserts.setdefault(op["id"], []).append(op["text"])
        elif kind == "update_shot":
            if shot_changed(op["index"]) or shots[op["index"]] is None:
                conflicts.append(op["op_id"])
                continue
            shots[op["index"]][op["field"]] = op["value"]  # type: ignore[index]
        elif kind == "delete_shot":
            if shot_changed(op["index"]) or shots[op["index"]] is None:
                conflicts.append(op["op_id"])
                continue
            shots[op["index"]] = None
        elif kind == "insert_shot":
            if op["after"] >= 0 and shot_changed(op["after"]):
                conflicts.append(op["op_id"])
                continue
            shot_inserts.setdefault(op["after"], []).append(op["shot"])
        elif kind == "move_shot":
            if base_draft is not None and (shot_changed(op["from"]) or shot_changed(op["to"])):
                conflicts.append(op["op_id"])
                continue
            moves.append((op["from"], op["to"]))
        applied.append(op["op_id"])

    body: list[str] = []
    for p in paras:
        if not p.get("_deleted"):
            body.append(p["text"])
        body.extend(inserts.get(p["id"], []))
    result["body"] = "\n\n".join(body)

    for src, dst in moves:
        item = shots.pop(src)
        shots.insert(dst, item)
    out_shots: list[dict] = list(shot_inserts.get(-1, []))
    for i, s in enumerate(shots):
        if s is not None:
            out_shots.append(s)
        out_shots.extend(shot_inserts.get(i, []))
    result["shots"] = out_shots
    StudioDraft.model_validate(result)  # 越界时抛错
    return result, applied, conflicts


# ── 生成 ─────────────────────────────────────────────────────────────


def _instruction_text(instructions: str, quick: str | None, n: int | None) -> str:
    parts = []
    if quick:
        parts.append(QUICK.get(quick, quick).format(n=n or 600))
    if instructions.strip():
        parts.append(instructions.strip())
    if not parts:
        raise ValidationError("写一句修改要求，或选一个快捷指令")
    return "；".join(parts)


async def _call_model(messages: list[dict]) -> tuple[Any, dict]:
    from app.services.llm import provider

    return await provider.call_llm_json_with_metadata(
        messages, temperature=0.4, max_tokens=6000, scene="studio_suggest", routing_group="default"
    )


async def create_suggestion(
    db: AsyncSession,
    project_id: int,
    *,
    scope: dict,
    instructions: str = "",
    quick: str | None = None,
    n: int | None = None,
    draft_token: str | None = None,
) -> dict:
    project = await ps.get_project(db, project_id)
    if project.finalized_version:
        raise ps.conflict("finalized", "已定稿，点「继续修改」后才能让 AI 修改")
    if draft_token and project.draft_token and draft_token != project.draft_token:
        raise ps.conflict("draft_conflict", "这份文稿在另一个窗口改过", draft_token=project.draft_token)
    spec = project.spec or {}
    draft = StudioDraft.model_validate(spec.get("draft") or {}).model_dump(mode="json")
    paras = ps.paragraphs_with_ids(draft.get("body", ""))
    if not paras and not draft.get("shots"):
        raise ValidationError("文稿是空的，先写点内容")
    text = _instruction_text(instructions, quick, n)
    scope = {"type": scope.get("type") or "all", **{k: v for k, v in scope.items() if k != "type"}}
    sources = await ps.list_sources(db, project_id)
    view = {
        "brief": ps.copy_brief(spec.get("brief")),
        "paragraphs": paras,
        "shots": [{"index": i, **s} for i, s in enumerate(draft.get("shots") or [])],
        "scope": scope,
        "sources": [
            {"n": i + 1, "title": s["snapshot"].get("title"), "summary": (s["snapshot"].get("summary") or "")[:400]}
            for i, s in enumerate(sources)
        ],
    }
    system = (
        "你是文稿编辑。按修改要求给出最少必要的修改，不重写未涉及的部分。只修改 scope 指定的段落或分镜"
        '（scope.type=all 表示全文）。返回 JSON：{"ops": [...]}，每个操作是以下之一：\n'
        '{"op":"replace_paragraph","id":"p_xxx","text":"新段落","reason":"为什么"}\n'
        '{"op":"insert_after","id":"p_xxx","text":"新段落"}\n'
        '{"op":"delete_paragraph","id":"p_xxx"}\n'
        '{"op":"update_shot","index":0,"field":"visual|camera|audio|caption|beat|prompt|transition|seconds","value":"…"}\n'
        '{"op":"insert_shot","after":0,"shot":{"seconds":3,"beat":"…","visual":"…","audio":"…"}}\n'
        '{"op":"delete_shot","index":0}  {"op":"move_shot","from":2,"to":0}\n'
        f"最多 {MAX_OPS} 个操作。事实只能来自已给来源，引用写成 [n]。"
    )
    try:
        reply, meta = await _call_model(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"修改要求：{text}\n\n{json.dumps(view, ensure_ascii=False)}"},
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("suggestion model failed: %s", str(exc)[:200])
        raise AppException("AI 修改失败，请检查模型配置或稍后重试", 503, {"code": "model_unavailable"}) from exc
    raw_ops = reply.get("ops") if isinstance(reply, dict) else reply
    ops = validate_ops(raw_ops or [], draft, scope)
    if not ops:
        raise AppException("AI 没有给出可用的修改，换个说法再试", 503, {"code": "model_unavailable"})
    sug = ProjectSuggestion(
        project_id=project_id,
        base_token=project.draft_token,
        scope={**scope, "quick": quick, "base_draft": draft},
        instructions=text,
        patch=ops,
        status="pending",
        applied_ops=[],
        model=(meta or {}).get("model") or (meta or {}).get("model_name"),
        cost=(meta or {}).get("cost"),
    )
    db.add(sug)
    await db.commit()
    return suggestion_dict(sug)


def suggestion_dict(s: ProjectSuggestion, conflicts: list[str] | None = None) -> dict:
    scope = {k: v for k, v in (s.scope or {}).items() if k != "base_draft"}
    data = {
        "id": s.id,
        "project_id": s.project_id,
        "scope": scope,
        "instructions": s.instructions,
        "ops": s.patch,
        "status": s.status,
        "applied_ops": s.applied_ops,
        "model": s.model,
        "cost": s.cost,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
    if conflicts is not None:
        data["conflicts"] = conflicts
    return data


async def _get(db: AsyncSession, suggestion_id: int) -> ProjectSuggestion:
    s = await db.get(ProjectSuggestion, suggestion_id)
    if not s:
        raise NotFoundError("修改建议", suggestion_id)
    return s


async def list_suggestions(db: AsyncSession, project_id: int) -> dict:
    rows = (
        await db.execute(
            select(ProjectSuggestion)
            .where(ProjectSuggestion.project_id == project_id)
            .order_by(ProjectSuggestion.id.desc())
            .limit(50)
        )
    ).scalars()
    return {"items": [suggestion_dict(s) for s in rows]}


async def apply_suggestion(db: AsyncSession, suggestion_id: int, op_ids: list[str] | None = None) -> dict:
    s = await _get(db, suggestion_id)
    if s.status in {"rejected", "applied"} or (s.scope or {}).get("closed"):
        raise ps.conflict("suggestion_closed", "这组建议已经处理过")
    project = await ps.get_project(db, s.project_id, lock=True)
    if project.finalized_version:
        raise ps.conflict("finalized", "已定稿，点「继续修改」后才能接受建议")
    done = set(s.applied_ops or [])
    wanted = [op for op in s.patch if op["op_id"] not in done and (op_ids is None or op["op_id"] in op_ids)]
    if not wanted:
        raise ValidationError("没有要接受的建议")
    current = StudioDraft.model_validate((project.spec or {}).get("draft") or {}).model_dump(mode="json")
    base = (s.scope or {}).get("base_draft")
    token_changed = bool(s.base_token and project.draft_token and s.base_token != project.draft_token)
    new_draft, applied, conflicts = apply_ops(current, wanted, base if token_changed else None)
    if applied:
        new_draft["provenance"] = "ai"
        res = await ps.write_draft_version(db, s.project_id, StudioDraft.model_validate(new_draft), "ai_suggestion")
    else:
        res = {"version": project.version, "draft_token": project.draft_token}
    s = await _get(db, suggestion_id)
    s.applied_ops = sorted(done | set(applied), key=lambda x: int(x[1:]))
    s.base_token = res["draft_token"] if applied else s.base_token
    if applied:
        s.scope = {**(s.scope or {}), "base_draft": new_draft}
    s.status = "applied" if len(s.applied_ops) == len(s.patch) else "partial" if s.applied_ops else s.status
    await db.commit()
    return {
        **suggestion_dict(s, conflicts),
        "draft": (await ps.draft_view(db, s.project_id)),
        "version": res["version"],
        "draft_token": res["draft_token"],
    }


async def reject_suggestion(db: AsyncSession, suggestion_id: int) -> dict:
    s = await _get(db, suggestion_id)
    if s.status == "pending":
        s.status = "rejected"
    elif s.status == "partial":  # 已接受的保留，其余视为拒绝
        s.scope = {**(s.scope or {}), "closed": True}
    await db.commit()
    return suggestion_dict(s)
