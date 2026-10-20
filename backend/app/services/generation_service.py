"""生成服务（改造方案第 8 节）与用灵感生图（创作工作台设计 6.5）。

* 服务：设置 · 生成服务里配置；Key 本地加密保存，接口里只回显末 4 位。接口格式先实现 OpenAI 兼容图像接口
  （``/images/generations``；服务声明支持参考图时带参考图走 ``/images/edits``）。厂商适配器按 ``api_format`` 扩展。
* 任务：``generation_jobs`` 一行一次生成，候选逐张落盘 ``data/generations/<job>/<i>.png`` 并推进度；
  每日上限按服务单独计（单价 × 张数），超出时拒绝并提示。
* 存入并使用：选中的候选写进灵感库（「生成图」，授权 AI 生成，记录提示词、模型、参数、参考条目，并和参考条目建
  generated 关联），同时加入项目素材放到目标位置。没选中的候选保留 7 天，由维护任务清理。
* 提示词起草：读目标处的文稿段落 / 分镜画面、所选风格、参考条目的描述，模型写草稿，可直接修改。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundError, ValidationError
from app.models.generation import GenerationJob, GenerationService
from app.models.library import LibraryItem

logger = logging.getLogger(__name__)

GEN_ROOT = (Path(__file__).resolve().parents[2] / "data" / "generations").resolve()
KEEP_DAYS = 7
MAX_N = 8
ASPECTS = ("1:1", "3:4", "4:3", "16:9", "9:16")
DEFAULT_SIZES = {"1:1": "1024x1024", "3:4": "1024x1536", "4:3": "1536x1024", "16:9": "1536x1024", "9:16": "1024x1536"}
# 目标决定默认画幅和素材角色（设计 6.5）
TARGET_DEFAULTS = {
    "moodboard": ("1:1", "moodboard"),
    "paragraph": ("16:9", "illustration"),
    "xhs": ("3:4", "illustration"),
    "cover": ("16:9", "cover"),
    "shot": ("16:9", "keyframe"),
    "mv": ("16:9", "keyframe"),
}
ACTIVE = {"queued", "running"}
SESSION_FACTORY = None  # 测试替换
_tasks: dict[int, asyncio.Task] = {}


def _session() -> AsyncSession:
    if SESSION_FACTORY is not None:
        return SESSION_FACTORY()
    from app.core.database import async_session

    return async_session()


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None


# ── 服务 ──


def mask_key(enc: str | None) -> str | None:
    from app.services.secret_store import decrypt_secret

    if not enc:
        return None
    try:
        raw = decrypt_secret(enc) or ""
    except Exception:  # noqa: BLE001
        logger.debug("忽略的异常（generation_service.py）", exc_info=True)
        return "（无法解密）"
    return f"…{raw[-4:]}" if raw else None


def service_dict(s: GenerationService, spent_today: float | None = None) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "kind": s.kind,
        "api_format": s.api_format,
        "base_url": s.base_url,
        "model": s.model,
        "capabilities": s.capabilities or {},
        "unit_price": s.unit_price,
        "daily_limit": s.daily_limit,
        "enabled": s.enabled,
        "is_default": s.is_default,
        "has_key": bool(s.api_key_enc),
        "key_hint": mask_key(s.api_key_enc),
        "spent_today": round(spent_today or 0.0, 4),
    }


async def spent_today(db: AsyncSession, service_id: int) -> float:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return float(
        (
            await db.execute(
                select(func.coalesce(func.sum(GenerationJob.cost), 0.0)).where(
                    GenerationJob.service_id == service_id,
                    GenerationJob.created_at >= start,
                    GenerationJob.status != "failed",
                )
            )
        ).scalar()
        or 0.0
    )


async def list_services(db: AsyncSession, kind: str | None = None) -> list[dict[str, Any]]:
    stmt = select(GenerationService).order_by(GenerationService.is_default.desc(), GenerationService.id)
    if kind:
        stmt = stmt.where(GenerationService.kind == kind)
    return [service_dict(s, await spent_today(db, s.id)) for s in (await db.execute(stmt)).scalars()]


def _validate_service(values: dict[str, Any]) -> None:
    url = str(values.get("base_url") or "")
    if url and not url.startswith(("http://", "https://")):
        raise ValidationError("地址需以 http(s):// 开头")
    from app.services.video_generation import ADAPTERS as VIDEO_ADAPTERS

    if values.get("api_format") and values["api_format"] not in ADAPTERS and values["api_format"] not in VIDEO_ADAPTERS:
        raise ValidationError(f"暂不支持接口格式 {values['api_format']}")
    caps = values.get("capabilities")
    if caps is not None and not isinstance(caps, dict):
        raise ValidationError("能力需为对象")


async def save_service(db: AsyncSession, values: dict[str, Any], service_id: int | None = None) -> dict[str, Any]:
    from app.services.secret_store import encrypt_secret

    _validate_service(values)
    if service_id is None:
        for k in ("name", "base_url", "model"):
            if not str(values.get(k) or "").strip():
                raise ValidationError("名称、地址、模型必填")
        s = GenerationService(capabilities={})
        db.add(s)
    else:
        s = await db.get(GenerationService, service_id)
        if s is None:
            raise NotFoundError("生成服务", service_id)
    for k in ("name", "kind", "api_format", "base_url", "model", "capabilities", "unit_price", "enabled"):
        if values.get(k) is not None:
            setattr(s, k, values[k].strip().rstrip("/") if k == "base_url" else values[k])
    if "daily_limit" in values:  # 允许清空（不限）
        s.daily_limit = values["daily_limit"]
    if values.get("api_key") is not None:
        s.api_key_enc = encrypt_secret(values["api_key"]) if values["api_key"].strip() else None
    if values.get("is_default"):
        for other in (await db.execute(select(GenerationService).where(GenerationService.kind == s.kind))).scalars():
            other.is_default = False
        s.is_default = True
    await db.commit()
    await db.refresh(s)
    return service_dict(s, await spent_today(db, s.id))


async def delete_service(db: AsyncSession, service_id: int) -> None:
    s = await db.get(GenerationService, service_id)
    if s is None:
        raise NotFoundError("生成服务", service_id)
    await db.delete(s)
    await db.commit()


async def _pick_service(db: AsyncSession, service_id: int | None, kind: str = "image") -> GenerationService | None:
    if service_id:
        s = await db.get(GenerationService, service_id)
        return s if s and s.enabled else None
    stmt = (
        select(GenerationService)
        .where(GenerationService.kind == kind, GenerationService.enabled.is_(True))
        .order_by(GenerationService.is_default.desc(), GenerationService.id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def available(db: AsyncSession) -> bool:
    return await _pick_service(db, None) is not None


# ── 适配器 ──


def size_for(service: GenerationService, aspect: str) -> str:
    sizes = (service.capabilities or {}).get("sizes") or {}
    return sizes.get(aspect) or DEFAULT_SIZES.get(aspect) or DEFAULT_SIZES["1:1"]


async def _decode(client: httpx.AsyncClient, data: list[dict[str, Any]]) -> list[bytes]:
    out = []
    for d in data:
        if d.get("b64_json"):
            out.append(base64.b64decode(d["b64_json"]))
        elif d.get("url"):
            r = await client.get(d["url"])
            r.raise_for_status()
            out.append(r.content)
    return out


async def openai_images(
    service: GenerationService, key: str | None, *, prompt: str, size: str, n: int, refs: list[Path]
) -> list[bytes]:
    """OpenAI 兼容图像接口：文生图 /images/generations；带参考图且服务支持时 /images/edits。"""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    base = service.base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=180) as client:
        if refs and (service.capabilities or {}).get("refs"):
            files = [("image[]", (p.name, p.read_bytes(), "image/png")) for p in refs[:4]]
            data = {"model": service.model, "prompt": prompt, "n": str(n), "size": size}
            r = await client.post(f"{base}/images/edits", headers=headers, data=data, files=files)
        else:
            body = {"model": service.model, "prompt": prompt, "n": n, "size": size}
            if (service.capabilities or {}).get("response_format", True):
                body["response_format"] = "b64_json"
            r = await client.post(f"{base}/images/generations", headers=headers, json=body)
        if r.status_code >= 400:
            try:
                msg = (r.json().get("error") or {}).get("message") or r.text
            except ValueError:
                msg = r.text
            raise AppException(f"生成服务返回 {r.status_code}：{str(msg)[:200]}", 502, {"code": "generation_failed"})
        return await _decode(client, r.json().get("data") or [])


Adapter = Callable[..., Awaitable[list[bytes]]]
ADAPTERS: dict[str, Adapter] = {"openai_images": openai_images}


# ── 提示词 ──


async def _ref_items(db: AsyncSession, ids: list[int]) -> list[LibraryItem]:
    if not ids:
        return []
    rows = {i.id: i for i in (await db.execute(select(LibraryItem).where(LibraryItem.id.in_(ids)))).scalars()}
    return [rows[i] for i in ids if i in rows]


def _ref_files(items: list[LibraryItem]) -> list[Path]:
    from app.services import library_files

    out = []
    for it in items:
        if it.file_path and (it.mime or "").startswith("image/"):
            try:
                p = library_files.abs_path(it.file_path)
            except Exception:  # noqa: BLE001
                logger.debug("忽略的异常（generation_service.py）", exc_info=True)
                continue
            if p.is_file():
                out.append(p)
    return out


def compose_prompt(prompt: str, refs: list[LibraryItem], with_images: bool) -> str:
    """服务不收参考图时，把参考条目的 AI 描述 / 提示词写进提示词。"""
    if with_images or not refs:
        return prompt
    notes = []
    for it in refs:
        desc = (it.ai_description or (it.body if it.kind in ("prompt", "generated") else "") or "").strip()
        if desc:
            notes.append(f"- {it.title}：{desc[:300]}")
    return prompt + ("\n\n参考：\n" + "\n".join(notes) if notes else "")


async def target_context(db: AsyncSession, project_id: int | None, target: dict[str, Any] | None) -> str:
    """目标处的文稿段落或分镜画面描述。"""
    if not project_id or not target:
        return ""
    from app.services import project_service as ps

    project = await ps.get_project(db, project_id)
    spec = project.spec or {}
    if project.finalized_version:
        spec = (await ps._revision(db, project_id, project.finalized_version)).spec or spec
    draft = spec.get("draft") or {}
    t = target.get("type")
    if t == "paragraph":
        for p in ps.paragraphs_with_ids(draft.get("body") or ""):
            if p["id"] == target.get("paragraph_id"):
                return f"文稿段落：{p['text']}"
    if t in ("shot", "mv") and str(target.get("shot") or "").isdigit():
        shots = draft.get("shots") or []
        i = int(target["shot"])
        if 1 <= i <= len(shots):
            s = shots[i - 1]
            return f"分镜 {i}：{s.get('beat') or ''}；画面：{s.get('visual') or ''}；提示词：{s.get('prompt') or ''}"
    if t in ("xhs", "cover"):
        return f"标题：{draft.get('title') or ''}\n梗概：{draft.get('logline') or ''}"
    return f"主题：{draft.get('title') or ''}"


async def style_rules_text(db: AsyncSession, style_id: str) -> str:
    """风格当前版本的规则（色板、字体、版式、动效）写成提示词片段。"""
    from app.services import styles

    try:
        st = await styles.get_style(db, style_id)
    except Exception:  # noqa: BLE001
        logger.debug("忽略的异常（generation_service.py）", exc_info=True)
        return ""
    cur = (
        next((v for v in st["versions"] if v["version"] == st["current_version"]), None)
        or (st["versions"] or [None])[0]
    )
    if not cur:
        return st["name"]
    parts = [st["name"]]
    if cur.get("palette"):
        parts.append("色板 " + "、".join(str(c.get("hex") if isinstance(c, dict) else c) for c in cur["palette"]))
    if cur.get("fonts"):
        parts.append("字体 " + "、".join(str(f.get("name") if isinstance(f, dict) else f) for f in cur["fonts"]))
    for k in ("layout_rules", "motion_rules", "note"):
        if cur.get(k):
            parts.append(str(cur[k])[:400])
    return "；".join(parts)


async def draft_prompt(
    db: AsyncSession,
    *,
    project_id: int | None,
    target: dict[str, Any] | None,
    style_id: str | None,
    ref_item_ids: list[int],
) -> dict[str, Any]:
    from app.services.llm.provider import call_llm_json

    ctx = await target_context(db, project_id, target)
    refs = await _ref_items(db, ref_item_ids)
    style_text = ""
    if style_id:
        style_text = await style_rules_text(db, style_id)
    lines = [f"- {r.title}：{(r.ai_description or r.body or '')[:300]}" for r in refs]
    try:
        reply = await call_llm_json(
            [
                {
                    "role": "system",
                    "content": "你是美术指导，写一条生图提示词：主体、构图、色彩、光线、质感、画面内文字（用「」标出，不超过 8 个字）。"
                    '风格规则必须体现在提示词里。只输出 JSON：{"prompt": "…"}',
                },
                {
                    "role": "user",
                    "content": f"目标：{ctx or '情绪板'}\n风格：{style_text or '不指定'}\n参考条目：\n"
                    + ("\n".join(lines) or "（无）"),
                },
            ],
            temperature=0.5,
            max_tokens=800,
            scene="image_prompt",
        )
    except Exception as exc:  # noqa: BLE001
        raise AppException("提示词起草失败，请检查模型配置", 503, {"code": "model_unavailable"}) from exc
    prompt = str((reply or {}).get("prompt") or "").strip() if isinstance(reply, dict) else ""
    if not prompt:
        raise AppException("模型没有给出提示词", 503, {"code": "model_unavailable"})
    return {"prompt": prompt[:4000], "context": ctx}


# ── 任务 ──


def job_dict(job: GenerationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "service_id": job.service_id,
        "model": job.model,
        "prompt": job.prompt,
        "ref_item_ids": job.ref_item_ids or [],
        "params": job.params or {},
        "target": job.target,
        "project_id": job.project_id,
        "output_id": job.output_id,
        "status": job.status,
        "progress": (job.params or {}).get("progress"),
        "results": [
            {**r, "url": f"/api/v1/generations/{job.id}/files/{r['index']}"} for r in job.results or [] if r.get("file")
        ],
        "cost": job.cost,
        "error": job.error,
        "created_at": _iso(job.created_at),
        "finished_at": _iso(job.finished_at),
    }


async def create_job(
    db: AsyncSession,
    *,
    prompt: str,
    ref_item_ids: list[int] | None = None,
    aspect: str | None = None,
    n: int = 4,
    service_id: int | None = None,
    project_id: int | None = None,
    output_id: int | None = None,
    target: dict[str, Any] | None = None,
    parent_job_id: int | None = None,
    parent_index: int | None = None,
    run_id: int | None = None,
    step_id: int | None = None,
    launch: bool = True,
) -> GenerationJob:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValidationError("先写提示词")
    service = await _pick_service(db, service_id)
    if service is None:
        raise AppException("还没有配置生成服务", 503, {"code": "generation_not_configured"})
    if service.kind != "image":
        raise ValidationError(f"「{service.name}」不是图片服务")
    caps = service.capabilities or {}
    n = max(1, min(int(n or 1), int(caps.get("max_n") or 4), MAX_N))
    ttype = (target or {}).get("type") or "moodboard"
    aspect = aspect if aspect in ASPECTS else TARGET_DEFAULTS.get(ttype, ("1:1", ""))[0]
    est = round(float(service.unit_price or 0) * n, 4)
    if service.daily_limit is not None:
        used = await spent_today(db, service.id)
        if used + est > float(service.daily_limit) + 1e-9:
            raise AppException(
                f"超过「{service.name}」每日上限：今天已用 ¥{used:.2f}，本次预计 ¥{est:.2f}，上限 ¥{service.daily_limit:.2f}",
                429,
                {"code": "generation_over_budget", "spent_today": used, "estimate": est},
            )
    refs = list(dict.fromkeys(int(i) for i in ref_item_ids or []))[:8]
    if parent_job_id is not None and parent_index is not None:
        parent = await db.get(GenerationJob, parent_job_id)
        if parent is None:
            raise NotFoundError("生成任务", parent_job_id)
        kept = next((r for r in parent.results or [] if r.get("index") == parent_index), None)
        if kept is None:
            raise ValidationError("没有这张候选")
        if not kept.get("library_item_id"):
            item = await _keep_one(db, parent, kept, role=None, target=None)
            kept["library_item_id"] = item.id
        refs = [kept["library_item_id"], *[r for r in refs if r != kept["library_item_id"]]]
    job = GenerationJob(
        kind="image",
        service_id=service.id,
        model=service.model,
        prompt=prompt[:8000],
        ref_item_ids=refs,
        params={
            "aspect": aspect,
            "size": size_for(service, aspect),
            "n": n,
            "estimate": est,
            "parent_job_id": parent_job_id,
        },
        target=target,
        project_id=project_id,
        output_id=output_id,
        run_id=run_id,
        step_id=step_id,
        status="queued",
        results=[],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    if launch:
        _tasks[job.id] = asyncio.create_task(_run_job_bg(job.id), name=f"generation-{job.id}")
    return job


async def _run_job_bg(job_id: int) -> None:
    try:
        async with _session() as db:
            await run_job(db, job_id)
    finally:
        _tasks.pop(job_id, None)


async def recover_interrupted() -> dict[str, int]:
    """启动时收拾上一次进程留下的任务：排队中的重新开跑；运行中的标为失败（可能已向厂商扣费，不自动重来，任务中心可重试）。"""
    from sqlalchemy import select

    requeued = failed = 0
    async with _session() as db:
        jobs = (
            (await db.execute(select(GenerationJob).where(GenerationJob.status.in_(("queued", "running")))))
            .scalars()
            .all()
        )
        for job in jobs:
            if job.status == "running":
                job.status = "failed"
                job.error = "后端重启时中断，可以重试"
                job.finished_at = datetime.now(UTC)
                failed += 1
        await db.commit()
        queued = [j.id for j in jobs if j.status == "queued"]
    for jid in queued:
        _tasks[jid] = asyncio.create_task(_run_job_bg(jid), name=f"generation-{jid}")
        requeued += 1
    return {"requeued": requeued, "failed": failed}


async def wait_job(job_id: int, timeout: float = 60) -> None:
    t = _tasks.get(job_id)
    if t is not None:
        await asyncio.wait_for(asyncio.shield(t), timeout)


async def run_job(db: AsyncSession, job_id: int) -> GenerationJob:
    from app.services.secret_store import decrypt_secret

    job = await db.get(GenerationJob, job_id, populate_existing=True)
    if job is None:
        raise NotFoundError("生成任务", job_id)
    service = await db.get(GenerationService, job.service_id) if job.service_id else None
    if service is None:
        job.status, job.error = "failed", "生成服务已删除"
        await db.commit()
        return job
    job.status = "running"
    await db.commit()
    refs = await _ref_items(db, job.ref_item_ids or [])
    files = _ref_files(refs) if (service.capabilities or {}).get("refs") else []
    prompt = compose_prompt(job.prompt, refs, bool(files))
    params = job.params or {}
    try:
        adapter = ADAPTERS[service.api_format]
        images = await adapter(
            service,
            decrypt_secret(service.api_key_enc) if service.api_key_enc else None,
            prompt=prompt,
            size=params.get("size") or size_for(service, params.get("aspect") or "1:1"),
            n=int(params.get("n") or 1),
            refs=files,
        )
        if not images:
            raise AppException("生成服务没有返回图片", 502)
        folder = GEN_ROOT / str(job.id)
        folder.mkdir(parents=True, exist_ok=True)
        results = []
        for i, data in enumerate(images[:MAX_N]):
            path = folder / f"{i}.png"
            path.write_bytes(data)
            results.append({"index": i, "file": str(path.relative_to(GEN_ROOT)), "library_item_id": None})
            job.results = list(results)  # 候选逐张出现
            await db.commit()
        job.cost = round(float(service.unit_price or 0) * len(results), 4)
        job.status = "done"
        job.params = {**params, "sent_refs": len(files), "final_prompt": prompt[:8000]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("generation job %s failed: %s", job_id, exc)
        job.status = "failed"
        job.error = (
            str(exc)[:500] if isinstance(exc, AppException | ValueError) else f"生成失败：{exc.__class__.__name__}"
        )
    job.finished_at = datetime.now(UTC)
    await db.commit()
    return job


async def get_job(db: AsyncSession, job_id: int) -> dict[str, Any]:
    job = await db.get(GenerationJob, job_id, populate_existing=True)
    if job is None:
        raise NotFoundError("生成任务", job_id)
    return job_dict(job)


async def list_jobs(db: AsyncSession, project_id: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    stmt = select(GenerationJob).order_by(GenerationJob.id.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(GenerationJob.project_id == project_id)
    return [job_dict(j) for j in (await db.execute(stmt)).scalars()]


def job_file(job: GenerationJob, index: int) -> Path:
    r = next((r for r in job.results or [] if r.get("index") == index), None)
    if r is None:
        raise NotFoundError("候选图", index)
    p = (GEN_ROOT / r["file"]).resolve()
    if not p.is_relative_to(GEN_ROOT) or not p.is_file():
        raise NotFoundError("候选图", index)
    return p


async def file_for(db: AsyncSession, job_id: int, index: int) -> Path:
    job = await db.get(GenerationJob, job_id)
    if job is None:
        raise NotFoundError("生成任务", job_id)
    return job_file(job, index)


async def _keep_one(
    db: AsyncSession, job: GenerationJob, result: dict[str, Any], *, role: str | None, target: dict[str, Any] | None
) -> LibraryItem:
    from app.models.library import ImportMethod, License, LinkRelation
    from app.services import library

    path = job_file(job, result["index"])
    is_video = path.suffix.lower() == ".mp4"
    item = await library.add_file(
        db,
        path.read_bytes(),
        f"generated-{job.id}-{result['index']}{path.suffix.lower() or '.png'}",
        mime="video/mp4" if is_video else "image/png",
        method=ImportMethod.GENERATED.value,
        title=job.prompt[:60],
        license=License.AI.value,
    )
    item.kind = "generated"
    item.license = License.AI.value
    item.body = job.prompt
    item.meta = {
        **(item.meta or {}),
        "prompt": job.prompt,
        "model": job.model,
        "service_id": job.service_id,
        "params": {k: v for k, v in (job.params or {}).items() if k in ("aspect", "size", "n", "seconds")},
        "ref_item_ids": job.ref_item_ids or [],
        "generation_job_id": job.id,
        "target": target or job.target,
    }
    await db.commit()
    for ref in job.ref_item_ids or []:
        if ref != item.id:
            await library.ensure_link(db, ("library", ref), ("library", item.id), LinkRelation.GENERATED.value)
    await db.commit()
    return item


async def keep(
    db: AsyncSession, job_id: int, indexes: list[int], *, role: str | None = None, target: dict[str, Any] | None = None
) -> dict[str, Any]:
    """存入并使用：选中的结果存入灵感库，并加入项目素材放到目标位置。"""
    from app.schemas.projects import AssetAdd
    from app.services import project_service as ps

    job = await db.get(GenerationJob, job_id, populate_existing=True)
    if job is None:
        raise NotFoundError("生成任务", job_id)
    if job.status != "done":
        raise ValidationError("生成还没完成")
    target = target if target is not None else job.target
    ttype = (target or {}).get("type") or "moodboard"
    role = role or TARGET_DEFAULTS.get(ttype, ("", "moodboard"))[1]
    results = [dict(r) for r in job.results or []]
    kept_items = []
    assets = []
    for r in results:
        if r["index"] not in indexes:
            continue
        if r.get("library_item_id"):
            item = await db.get(LibraryItem, r["library_item_id"])
        else:
            item = await _keep_one(db, job, r, role=role, target=target)
            r["library_item_id"] = item.id
        kept_items.append(item.id)
        if job.project_id:
            asset_target = {k: v for k, v in (target or {}).items() if k != "type"} or None
            if job.output_id and asset_target is not None:
                asset_target.setdefault("output_id", job.output_id)
            assets.append(
                await ps.add_asset(
                    db, job.project_id, AssetAdd(library_item_id=item.id, role=role, target=asset_target)
                )
            )
    if not kept_items:
        raise ValidationError("先选一张")
    job.results = results
    await db.commit()
    return {"job": job_dict(job), "library_item_ids": kept_items, "assets": assets}


async def keyframe_for_flow(
    db: AsyncSession,
    *,
    project_id: int,
    output_id: int,
    shot: int,
    prompt: str,
    aspect_ratio: str,
    run_id: int | None = None,
    step_id: int | None = None,
) -> int | None:
    """成片流程的美术：生一张关键帧，直接存入灵感库并挂到项目素材（keyframe，target={shot, output_id}）。"""
    try:
        job = await create_job(
            db,
            prompt=prompt,
            aspect=aspect_ratio,
            n=1,
            project_id=project_id,
            output_id=output_id,
            target={"type": "shot", "shot": shot},
            run_id=run_id,
            step_id=step_id,
            launch=False,
        )
        job = await run_job(db, job.id)
        if job.status != "done" or not job.results:
            return None
        res = await keep(db, job.id, [job.results[0]["index"]], role="keyframe")
        return res["library_item_ids"][0]
    except Exception:  # noqa: BLE001
        logger.warning("keyframe generation failed for project %s shot %s", project_id, shot, exc_info=True)
        await db.rollback()
        return None


def cleanup_candidates(now: datetime | None = None) -> int:
    """没选中的候选保留 7 天（选中的已复制进灵感库）。按目录修改时间删除。"""
    now = now or datetime.now(UTC)
    if not GEN_ROOT.exists():
        return 0
    n = 0
    cutoff = (now - timedelta(days=KEEP_DAYS)).timestamp()
    for d in GEN_ROOT.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n


async def test_service(db: AsyncSession, service_id: int) -> dict[str, Any]:
    """测试连接：图像服务生一张最小尺寸的图（计入花费）；视频服务只查一次任务列表（不产生费用）。"""
    service = await db.get(GenerationService, service_id)
    if service is None:
        raise NotFoundError("生成服务", service_id)
    if service.kind == "video":
        from app.services import video_generation

        return await video_generation.test_connection(service)
    job = await create_job(db, prompt="a red circle on white background", n=1, service_id=service_id, launch=False)
    job = await run_job(db, job.id)
    return {"ok": job.status == "done", "error": job.error, "job_id": job.id}
