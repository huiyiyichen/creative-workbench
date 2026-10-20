"""视频生成接口（改造方案第 8 节）：`generate_video(prompt, first_frame, duration, aspect) → 任务`。

厂商视频生成都是异步的：提交 → 拿到厂商任务 id → 轮询状态 → 下载结果到本地。这里按 `api_format` 扩展适配器，
每个适配器实现 `submit` 和 `poll` 两步；任务记在 `generation_jobs`（kind=video），厂商任务 id 和进度写在
`params.vendor_task_id / progress`，所以服务重启后能接着轮询（`resume_pending`）。任务进任务中心；完成后
可「存入并使用」（灵感库 + 项目素材，分镜目标时挂到对应镜头）。

先实现 OpenAI 兼容的视频接口（`/videos`：创建、查询、`/videos/{id}/content` 下载）。单价按「元 / 秒」计，
每日上限与生图共用服务的设置。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundError, ValidationError
from app.models.generation import GenerationJob, GenerationService
from app.models.library import LibraryItem
from app.services import generation_service as gen

logger = logging.getLogger(__name__)

ASPECTS = ("16:9", "9:16", "1:1")
DEFAULT_SIZES = {"16:9": "1280x720", "9:16": "720x1280", "1:1": "1024x1024"}
DURATIONS = (4, 5, 6, 8, 10, 12)
POLL_SECONDS = 5.0
TIMEOUT_SECONDS = 30 * 60
_tasks: dict[int, asyncio.Task] = {}


@dataclass
class Submitted:
    task_id: str


@dataclass
class Polled:
    status: str  # running / done / failed
    progress: int | None = None
    error: str | None = None
    data: bytes | None = None


@dataclass
class VideoAdapter:
    submit: Callable[..., Awaitable[Submitted]]
    poll: Callable[..., Awaitable[Polled]]


def _err(r: httpx.Response) -> str:
    try:
        body = r.json()
        msg = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else body.get("error")
        return str(msg or r.text)[:200]
    except ValueError:
        return r.text[:200]


async def _openai_submit(
    service: GenerationService,
    key: str | None,
    *,
    prompt: str,
    seconds: int,
    size: str,
    first_frame: Path | None,
) -> Submitted:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    base = service.base_url.rstrip("/")
    data = {"model": service.model, "prompt": prompt, "seconds": str(seconds), "size": size}
    async with httpx.AsyncClient(timeout=120) as client:
        if first_frame is not None:
            files = {"input_reference": (first_frame.name, first_frame.read_bytes(), "image/png")}
            r = await client.post(f"{base}/videos", headers=headers, data=data, files=files)
        else:
            r = await client.post(f"{base}/videos", headers=headers, json={**data, "seconds": str(seconds)})
    if r.status_code >= 400:
        raise AppException(f"视频服务返回 {r.status_code}：{_err(r)}", 502, {"code": "generation_failed"})
    tid = (r.json() or {}).get("id")
    if not tid:
        raise AppException("视频服务没有返回任务 id", 502)
    return Submitted(task_id=str(tid))


async def _openai_poll(service: GenerationService, key: str | None, *, task_id: str) -> Polled:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    base = service.base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        r = await client.get(f"{base}/videos/{task_id}", headers=headers)
        if r.status_code >= 400:
            return Polled(status="failed", error=f"查询任务失败：HTTP {r.status_code} {_err(r)}")
        body = r.json() or {}
        status = str(body.get("status") or "")
        progress = body.get("progress")
        if status in ("failed", "cancelled", "canceled", "expired"):
            err = body.get("error")
            msg = err.get("message") if isinstance(err, dict) else err
            return Polled(status="failed", error=str(msg or f"厂商任务{status}")[:300])
        if status not in ("completed", "succeeded", "success"):
            return Polled(status="running", progress=int(progress) if isinstance(progress, int | float) else None)
        c = await client.get(f"{base}/videos/{task_id}/content", headers=headers)
        if c.status_code >= 400:
            return Polled(status="failed", error=f"下载成片失败：HTTP {c.status_code}")
        return Polled(status="done", progress=100, data=c.content)


ADAPTERS: dict[str, VideoAdapter] = {"openai_videos": VideoAdapter(submit=_openai_submit, poll=_openai_poll)}


def size_for(service: GenerationService, aspect: str) -> str:
    sizes = (service.capabilities or {}).get("sizes") or {}
    return sizes.get(aspect) or DEFAULT_SIZES.get(aspect) or DEFAULT_SIZES["16:9"]


async def _first_frame_path(db: AsyncSession, item_id: int | None) -> Path | None:
    if not item_id:
        return None
    item = await db.get(LibraryItem, item_id)
    if item is None:
        raise ValidationError("首帧条目不存在")
    files = gen._ref_files([item])
    if not files:
        raise ValidationError("首帧条目没有图片文件")
    return files[0]


async def create_video_job(
    db: AsyncSession,
    *,
    prompt: str,
    first_frame_item_id: int | None = None,
    duration: int = 5,
    aspect: str | None = None,
    service_id: int | None = None,
    project_id: int | None = None,
    output_id: int | None = None,
    target: dict[str, Any] | None = None,
    launch: bool = True,
) -> GenerationJob:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValidationError("先写提示词")
    service = await gen._pick_service(db, service_id, kind="video")
    if service is None or service.kind != "video":
        raise AppException("还没有配置视频生成服务", 503, {"code": "generation_not_configured"})
    if service.api_format not in ADAPTERS:
        raise ValidationError(f"「{service.name}」的接口格式 {service.api_format} 不能生成视频")
    caps = service.capabilities or {}
    allowed = [int(d) for d in caps.get("durations") or DURATIONS]
    seconds = int(duration or allowed[0])
    if seconds not in allowed:
        raise ValidationError(f"时长只能是 {'、'.join(str(d) for d in allowed)} 秒")
    aspect = aspect if aspect in ASPECTS else "16:9"
    if first_frame_item_id and not caps.get("first_frame", True):
        raise ValidationError(f"「{service.name}」不支持首帧")
    est = round(float(service.unit_price or 0) * seconds, 4)
    if service.daily_limit is not None:
        used = await gen.spent_today(db, service.id)
        if used + est > float(service.daily_limit) + 1e-9:
            raise AppException(
                f"超过「{service.name}」每日上限：今天已用 ¥{used:.2f}，本次预计 ¥{est:.2f}，上限 ¥{service.daily_limit:.2f}",
                429,
                {"code": "generation_over_budget", "spent_today": used, "estimate": est},
            )
    if first_frame_item_id:
        await _first_frame_path(db, first_frame_item_id)  # 提前校验
    job = GenerationJob(
        kind="video",
        service_id=service.id,
        model=service.model,
        prompt=prompt[:8000],
        ref_item_ids=[first_frame_item_id] if first_frame_item_id else [],
        params={
            "aspect": aspect,
            "size": size_for(service, aspect),
            "seconds": seconds,
            "n": 1,
            "estimate": est,
            "first_frame_item_id": first_frame_item_id,
            "progress": 0,
        },
        target=target,
        project_id=project_id,
        output_id=output_id,
        status="queued",
        results=[],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    if launch:
        launch_job(job.id)
    return job


def launch_job(job_id: int) -> None:
    if job_id in _tasks:
        return
    _tasks[job_id] = asyncio.create_task(_run_bg(job_id), name=f"video-generation-{job_id}")


async def _run_bg(job_id: int) -> None:
    try:
        async with gen._session() as db:
            await run_video_job(db, job_id)
    except Exception:  # noqa: BLE001
        logger.warning("video job %s crashed", job_id, exc_info=True)
    finally:
        _tasks.pop(job_id, None)


async def wait_job(job_id: int, timeout: float = 60) -> None:
    t = _tasks.get(job_id)
    if t is not None:
        await asyncio.wait_for(asyncio.shield(t), timeout)


async def _fail(db: AsyncSession, job: GenerationJob, msg: str) -> GenerationJob:
    job.status = "failed"
    job.error = msg[:500]
    job.finished_at = datetime.now(UTC)
    await db.commit()
    return job


async def run_video_job(db: AsyncSession, job_id: int) -> GenerationJob:
    """提交（没提交过时）→ 轮询到完成 / 失败 / 超时 → 下载到 data/generations/<job>/0.mp4。"""
    from app.services.secret_store import decrypt_secret

    job = await db.get(GenerationJob, job_id, populate_existing=True)
    if job is None:
        raise NotFoundError("生成任务", job_id)
    if job.status not in gen.ACTIVE:
        return job
    service = await db.get(GenerationService, job.service_id) if job.service_id else None
    if service is None or service.api_format not in ADAPTERS:
        return await _fail(db, job, "视频生成服务已删除或接口格式不支持")
    adapter = ADAPTERS[service.api_format]
    key = decrypt_secret(service.api_key_enc) if service.api_key_enc else None
    params = dict(job.params or {})
    try:
        if not params.get("vendor_task_id"):
            frame = await _first_frame_path(db, params.get("first_frame_item_id"))
            sub = await adapter.submit(
                service,
                key,
                prompt=job.prompt,
                seconds=int(params.get("seconds") or 5),
                size=params.get("size") or size_for(service, params.get("aspect") or "16:9"),
                first_frame=frame,
            )
            params["vendor_task_id"] = sub.task_id
            params["submitted_at"] = datetime.now(UTC).isoformat()
        job.status = "running"
        job.params = dict(params)
        await db.commit()
        started = datetime.fromisoformat(params["submitted_at"])
        while True:
            res = await adapter.poll(service, key, task_id=params["vendor_task_id"])
            if res.status == "failed":
                return await _fail(db, job, res.error or "厂商任务失败")
            if res.status == "done":
                if not res.data:
                    return await _fail(db, job, "视频服务没有返回文件")
                folder = gen.GEN_ROOT / str(job.id)
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / "0.mp4"
                path.write_bytes(res.data)
                job.results = [
                    {"index": 0, "file": str(path.relative_to(gen.GEN_ROOT)), "library_item_id": None, "kind": "video"}
                ]
                job.cost = round(float(service.unit_price or 0) * int(params.get("seconds") or 0), 4)
                job.params = {**params, "progress": 100}
                job.status = "done"
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return job
            if res.progress is not None and res.progress != params.get("progress"):
                params["progress"] = res.progress
                job.params = dict(params)
                await db.commit()
            if (datetime.now(UTC) - started).total_seconds() > TIMEOUT_SECONDS:
                return await _fail(db, job, "视频生成超过 30 分钟，已停止等待；厂商那边可能仍在生成")
            await asyncio.sleep(POLL_SECONDS)
    except AppException as exc:
        return await _fail(db, job, exc.message)
    except httpx.HTTPError as exc:
        return await _fail(db, job, f"连接视频服务失败：{exc.__class__.__name__}")


async def resume_pending() -> int:
    """服务重启后：已提交到厂商、还没结束的视频任务接着轮询；没提交的标为失败可重试。"""
    n = 0
    async with gen._session() as db:
        jobs = (
            (
                await db.execute(
                    select(GenerationJob).where(GenerationJob.kind == "video", GenerationJob.status.in_(gen.ACTIVE))
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            if (job.params or {}).get("vendor_task_id"):
                launch_job(job.id)
                n += 1
            else:
                job.status = "failed"
                job.error = "服务重启时还没提交到厂商，请重新生成"
                job.finished_at = datetime.now(UTC)
        await db.commit()
    return n


async def test_connection(service: GenerationService) -> dict[str, Any]:
    """视频服务测试连接：查一次任务列表，不提交生成。"""
    from app.services.secret_store import decrypt_secret

    key = decrypt_secret(service.api_key_enc) if service.api_key_enc else None
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{service.base_url.rstrip('/')}/videos", headers=headers, params={"limit": 1})
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"连接失败：{exc.__class__.__name__}", "job_id": None}
    if r.status_code >= 400:
        return {"ok": False, "error": f"视频服务返回 {r.status_code}：{_err(r)}", "job_id": None}
    return {"ok": True, "error": None, "job_id": None}
