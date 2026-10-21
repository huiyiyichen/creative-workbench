"""成稿流程的角色（创作工作台设计 7.1）：写手 → 审校 → 写手修改 →〔接受〕→ 写入文稿。

* 写手（writer，params.mode = draft | revise）：按项目设定、来源快照、所选方向和内容模板写完整文稿；
  修改模式读原稿和审校意见，逐条处理。正文段落与来源的引用关系登记为产物来源（段落锚点）。
* 审校（reviewer）：只提意见不改稿，每条意见指向段落编号，给出问题与改法；没有问题时 passed=True。
* 写入文稿（apply_draft）：关卡接受（或关卡关闭）后把最终稿写成项目的新版本（原因 ai），不接受则跳过。
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.studio import StudioDraft
from app.services import prompt_kit
from app.services.flows.roles import ArtifactOut, RoleContext, RoleError, _llm

MAX_ISSUES = 20


# ── 项目上下文 ──


async def project_context(ctx: RoleContext) -> dict[str, Any]:
    from app.services import project_service as ps

    pid = ctx.inputs.get("project_id")
    if not str(pid or "").isdigit():
        raise RoleError("成稿流程需要项目")
    project = await ps.get_project(ctx.db, int(pid))
    spec = project.spec or {}
    brief = ps.copy_brief(spec.get("brief"))
    sources = await ps.list_sources(ctx.db, project.id)
    idea = spec.get("idea") or {}
    return {"project": project, "brief": brief, "sources": sources, "idea": idea, "template": spec.get("template")}


def sources_text(sources: list[dict[str, Any]]) -> str:
    lines = []
    for i, s in enumerate(sources, 1):
        snap = s.get("snapshot") or {}
        role = "主来源" if s.get("role") == "main" else "参考"
        meta = "，".join(x for x in [snap.get("platform"), snap.get("published_at")] if x)
        lines.append(f"[{i}] （{role}）{snap.get('title') or '未命名'}{f'（{meta}）' if meta else ''}")
        summary = (snap.get("summary") or "").strip()
        if summary:
            lines.append(f"    摘要：{summary[:600]}")
    return "\n".join(lines) or "（没有来源）"


def source_link(source: dict[str, Any], anchor: str | None) -> dict[str, Any] | None:
    if source.get("content_id"):
        return {"relation": "cites", "target_type": "content", "target_id": source["content_id"], "anchor": anchor}
    if source.get("library_item_id"):
        return {"relation": "cites", "target_type": "library", "target_id": source["library_item_id"], "anchor": anchor}
    return None


def citation_links(
    body: str, citations: Any, sources: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """模型返回 [{paragraph: 段落序号(从 1), sources: [来源序号]}] → 段落锚点的引用关系。

    只保留真实存在的段落和来源；返回 (links, 规范化后的 citations)。
    """
    from app.services.project_service import paragraphs_with_ids

    paras = paragraphs_with_ids(body)
    links: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []
    for c in citations if isinstance(citations, list) else []:
        if not isinstance(c, dict):
            continue
        try:
            pi = int(c.get("paragraph"))
        except (TypeError, ValueError):
            continue
        if not 1 <= pi <= len(paras):
            continue
        used = []
        for si in c.get("sources") or []:
            try:
                si = int(si)
            except (TypeError, ValueError):
                continue
            if 1 <= si <= len(sources) and si not in used:
                ln = source_link(sources[si - 1], paras[pi - 1]["id"])
                if ln:
                    links.append(ln)
                    used.append(si)
        if used:
            clean.append({"paragraph_id": paras[pi - 1]["id"], "sources": used})
    return links, clean


def coerce_draft(raw: Any, brief: dict[str, Any], previous: dict[str, Any] | None = None) -> StudioDraft:
    from app.services.project_service import studio_brief
    from app.services.studio_service import _coerce_ai_draft

    if not isinstance(raw, dict):
        raise RoleError("写手没有返回 JSON 对象")
    candidate = raw.get("draft") if isinstance(raw.get("draft"), dict) else raw
    prev = StudioDraft.model_validate(previous or {})
    try:
        return _coerce_ai_draft(candidate, studio_brief(brief), prev)
    except ValueError as exc:
        raise RoleError(str(exc)) from exc


MODE_DIRECTION = {
    "article": (
        "这是文章。body 是完整、可直接发布的正文，段落之间空一行；shots 与 cues 为 []。"
        "结构：开头从一个具体事件、数据或场景切入，前三段内让读者知道这篇能给他什么；中间每段一个观点配一个例子或数据，"
        "多个案例从弱到强排；结尾落在一个明确判断或下一步行动上。"
    ),
    "video_prompt": (
        "这是视频。body 写可直接朗读的口播旁白（段落之间空一行），第一句就是钩子，不自我介绍；单句不超过 30 字，"
        "按每秒约 4–5 个字控制总字数。shots 写画面、镜头、声音和剪辑，约每 2–3 秒一个画面变化。"
    ),
    "animation_video": (
        "这是动画讲解视频。body 写可直接朗读的完整中文旁白（段落之间空一行）。"
        "shots 用图形、图表、标注、数字和关系变化解释概念，每个 audio 写对应旁白。"
    ),
    "music_video": "这是音乐 MV。body 写视觉概念与段落情绪；shots 按前奏、主歌、副歌、桥段、尾奏组织。",
}


def _draft_digest(draft: dict[str, Any]) -> str:
    from app.services.project_service import paragraphs_with_ids

    lines = [f"标题：{draft.get('title') or ''}", f"梗概：{draft.get('logline') or ''}", "正文："]
    for i, p in enumerate(paragraphs_with_ids(draft.get("body") or ""), 1):
        lines.append(f"[{i}] {p['text']}")
    shots = draft.get("shots") or []
    if shots:
        lines.append("分镜：")
        for i, s in enumerate(shots, 1):
            lines.append(
                f"  镜 {i}（{s.get('seconds')} 秒）{s.get('beat') or ''}：{s.get('visual') or ''} / 旁白：{s.get('audio') or ''}"
            )
    return "\n".join(lines)


# ── 写手 ──


async def writer(ctx: RoleContext) -> list[ArtifactOut]:
    pc = await project_context(ctx)
    brief = pc["brief"]
    if not brief.get("theme"):
        raise RoleError("先写一个主题")
    mode = str(ctx.node.params.get("mode") or "draft")
    sources = pc["sources"]
    common = (
        "你是资深内容作者，按作者给的主题、受众、语气和所选方向写一稿可以直接发布的内容。只输出一个 JSON 对象："
        '{"title": "…", "logline": "一段梗概", "body": "正文", "shots": [{"seconds": 8, "beat": "…", "visual": "…", '
        '"camera": "…", "audio": "…", "transition": "直切", "caption": "…", "prompt": "…"}], "cues": [], '
        '"citations": [{"paragraph": 1, "sources": [1]}], "summary": "一句话说明这一稿"}。'
        + MODE_DIRECTION.get(brief.get("mode") or "article", "")
        + "用到来源的段落在 citations 里写明段落序号（从 1 开始，按空行分段）和来源序号。"
        + "\n"
        + prompt_kit.WRITER_RULES
    )
    if brief.get("mode") not in (None, "article"):
        common += f"分镜总时长约 {brief.get('duration_seconds') or 180:g} 秒。"
    user: dict[str, Any] = {
        "主题": brief.get("theme"),
        "内容形态": brief.get("mode"),
        "受众": brief.get("audience"),
        "语气": brief.get("tone"),
        "创作思路": brief.get("intent"),
        "所选方向": pc["idea"].get("custom") or pc["idea"].get("chosen"),
        "内容模板": pc["template"],
        "来源": sources_text(sources),
    }
    links: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    if mode == "revise":
        draft_art = ctx.latest("draft")
        review = ctx.latest("review")
        if draft_art is None:
            raise RoleError("没有原稿可改")
        previous = (draft_art.get("content") or {}).get("draft") or {}
        issues = ((review or {}).get("content") or {}).get("issues") or []
        links.append({"relation": "derived_from", "target_type": "artifact", "target_id": draft_art["id"]})
        if review:
            links.append({"relation": "derived_from", "target_type": "artifact", "target_id": review["id"]})
        if not issues:
            # 审校没有意见：原稿直接通过，不再调用模型
            content = {**(draft_art.get("content") or {}), "summary": "审校没有意见，保留原稿", "revised": False}
            return [ArtifactOut("draft", f"文稿 · 第 {ctx.round} 稿（未改）", content, links + _carry_cites(draft_art))]
        system = (
            common
            + "\n现在是修改稿：以原稿为底，逐条处理审校意见。"
            + prompt_kit.REVISE_RULES
            + '另外输出 resolved：[{"issue": "意见编号", "how": "怎么改的"}]。'
            + ctx.system_extra()
        )
        user["原稿"] = _draft_digest(previous)
        user["审校意见"] = [
            {"编号": i["id"], "段落": i.get("paragraph"), "问题": i.get("problem"), "改法": i.get("suggestion")}
            for i in issues
        ]
    else:
        system = common + ctx.system_extra()
    reply = await _llm(
        ctx,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"运行 #{ctx.run_id}\n" + json.dumps(user, ensure_ascii=False, default=str)},
        ],
        scene="flow_writer",
        max_tokens=12000,
    )
    draft = coerce_draft(reply, brief, previous)
    payload = draft.model_dump(mode="json")
    cite_links, citations = citation_links(payload["body"], reply.get("citations"), sources)
    content = {
        "draft": payload,
        "citations": citations,
        "summary": str(reply.get("summary") or "").strip()[:300]
        or (f"按 {len(user.get('审校意见') or [])} 条意见修改" if mode == "revise" else "初稿"),
        "round": ctx.round,
        "mode": mode,
    }
    if mode == "revise":
        content["resolved"] = [r for r in reply.get("resolved") or [] if isinstance(r, dict)][:MAX_ISSUES]
        content["revised"] = True
    title = "文稿 · 修改稿" if mode == "revise" else "文稿 · 初稿"
    return [ArtifactOut("draft", title, content, links + cite_links)]


def _carry_cites(art: dict[str, Any]) -> list[dict[str, Any]]:
    """原稿未改时，沿用它的段落引用（溯源时段落锚点仍然准确）。"""
    out = []
    for ln in art.get("links") or []:
        if ln.get("relation") == "cites" and ln.get("target_type") in ("content", "library"):
            out.append({k: ln.get(k) for k in ("relation", "target_type", "target_id", "anchor")})
    return out


# ── 审校 ──


async def reviewer(ctx: RoleContext) -> list[ArtifactOut]:
    pc = await project_context(ctx)
    draft_art = ctx.latest("draft")
    if draft_art is None:
        raise RoleError("没有文稿可审")
    from app.services.project_service import paragraphs_with_ids

    draft = (draft_art.get("content") or {}).get("draft") or {}
    paras = paragraphs_with_ids(draft.get("body") or "")
    system = (
        "你是资深内容编辑，替作者审一稿准备发布的内容。"
        + prompt_kit.REVIEW_RULES
        + f"最多 {MAX_ISSUES} 条，按严重程度排序。只输出 JSON："
        '{"summary": "总体评价一两句", "issues": [{"paragraph": 段落序号或 null, "shot": 分镜序号或 null, '
        '"severity": "high|medium|low", "problem": "问题", "suggestion": "改法"}]}。没有问题时 issues 为 []。'
        + ctx.system_extra()
    )
    user = {
        "主题": pc["brief"].get("theme"),
        "受众": pc["brief"].get("audience"),
        "语气": pc["brief"].get("tone"),
        "来源": sources_text(pc["sources"]),
        "文稿": _draft_digest(draft),
    }
    reply = await _llm(
        ctx,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"运行 #{ctx.run_id}\n" + json.dumps(user, ensure_ascii=False)},
        ],
        scene="flow_reviewer",
        max_tokens=3000,
    )
    if not isinstance(reply, dict):
        raise RoleError("审校没有返回 JSON 对象")
    shots = len(draft.get("shots") or [])
    issues = []
    for raw in reply.get("issues") or []:
        if not isinstance(raw, dict) or not str(raw.get("problem") or "").strip():
            continue
        para = raw.get("paragraph")
        para = int(para) if str(para or "").isdigit() and 1 <= int(para) <= len(paras) else None
        shot = raw.get("shot")
        shot = int(shot) if str(shot or "").isdigit() and 1 <= int(shot) <= shots else None
        sev = raw.get("severity") if raw.get("severity") in ("high", "medium", "low") else "medium"
        issues.append(
            {
                "id": f"r{len(issues) + 1}",
                "paragraph": para,
                "paragraph_id": paras[para - 1]["id"] if para else None,
                "shot": shot,
                "severity": sev,
                "problem": str(raw["problem"]).strip()[:500],
                "suggestion": str(raw.get("suggestion") or "").strip()[:800],
            }
        )
        if len(issues) >= MAX_ISSUES:
            break
    content = {
        "summary": str(reply.get("summary") or "").strip()[:300] or f"意见 {len(issues)} 条",
        "issues": issues,
        "passed": not issues,
        "draft_artifact_id": draft_art["id"],
    }
    links = [{"relation": "reviews", "target_type": "artifact", "target_id": draft_art["id"]}]
    for i in issues:
        if i["paragraph_id"]:
            links.append(
                {
                    "relation": "reviews",
                    "target_type": "artifact",
                    "target_id": draft_art["id"],
                    "anchor": i["id"],
                    "target_anchor": i["paragraph_id"],
                }
            )
    return [ArtifactOut("review", f"审校意见 · {len(issues)} 条", content, links)]


# ── 写入文稿 ──


async def apply_draft(ctx: RoleContext) -> list[ArtifactOut]:
    from app.services import project_service as ps

    gate = next((v for v in ctx.decisions.values() if isinstance(v, dict)), None)
    if gate and gate.get("card_id") == "reject":
        ctx.summary = "未接受，文稿不变"
        return []
    draft_art = ctx.latest("draft")
    if draft_art is None:
        raise RoleError("没有可写入的文稿")
    pc = await project_context(ctx)
    project = pc["project"]
    if project.finalized_version:
        raise RoleError("项目已定稿，点「继续修改」后再写入")
    draft = StudioDraft.model_validate({**((draft_art.get("content") or {}).get("draft") or {}), "provenance": "ai"})
    res = await ps.write_draft_version(ctx.db, project.id, draft, "ai")
    content = {
        "project_id": project.id,
        "version": res["version"],
        "draft_artifact_id": draft_art["id"],
        "summary": f"写入文稿 v{res['version']}",
    }
    links = [{"relation": "derived_from", "target_type": "artifact", "target_id": draft_art["id"]}]
    return [ArtifactOut("draft_version", f"文稿 v{res['version']}", content, links + _carry_cites(draft_art))]


ROLES = {"writer": writer, "reviewer": reviewer, "apply_draft": apply_draft}
