"""成片回传（设计 6.3）：外部 agent（Claude Code / Codex / 其他）按提示词包做完视频后，把成片交回工作台。

两条路：产出页「回传成片」上传文件；或外部 agent 通过工作台工具 `upload_output`（本机文件路径或下载地址）。
回传的成片存成该产出物的一个制作物（ProjectArtifact，`progress.source` 记来源），产出物标为完成，
`content.deliveries` 留一条记录；之后在产出页、作品库里预览和下载。
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.project import ProjectArtifact
from app.services import project_service as ps

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
MAX_BYTES = 4 * 1024 * 1024 * 1024
DELIVERABLE_KINDS = {"prompt_bundle", "video", "mv"}
SOURCES = {"upload": "上传", "agent": "外部 agent"}


def media_root() -> Path:
    from app.services import studio_service

    return studio_service.MEDIA_ROOT


def check_name(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in VIDEO_EXTS:
        raise ValidationError(f"只支持视频文件（{'、'.join(sorted(VIDEO_EXTS))}）")
    return ext


async def _probe_duration(path: Path) -> float | None:
    try:
        from app.services.studio_media import run_process, tool

        meta = json.loads(
            await run_process(
                [tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]
            )
        )
        return round(float(meta["format"]["duration"]), 2)
    except Exception:  # noqa: BLE001
        return None


async def staging_path(output_id: int, filename: str) -> Path:
    """上传先写到这里，再交给 attach。"""
    ext = check_name(filename)
    folder = media_root() / "deliveries" / "_incoming"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{output_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}{ext}"


async def attach(
    db: AsyncSession,
    output_id: int,
    file: Path,
    *,
    filename: str,
    source: str = "upload",
    note: str | None = None,
    move: bool = False,
) -> dict[str, Any]:
    output = await ps.get_output(db, output_id)
    if output.kind not in DELIVERABLE_KINDS:
        raise ValidationError("只有提示词包、讲解视频和 MV 能回传成片")
    ext = check_name(filename)
    if not file.is_file():
        raise ValidationError("文件不存在")
    size = file.stat().st_size
    if size == 0:
        raise ValidationError("文件是空的")
    if size > MAX_BYTES:
        raise ValidationError("文件超过 4 GB")
    project = await ps.get_project(db, output.project_id)
    version = output.based_on_version or project.finalized_version or project.version
    art = ProjectArtifact(
        project_id=project.id,
        version=version,
        kind="mv" if output.kind == "mv" else "video",
        status="queued",
        output_id=output.id,
        progress={},
        settings={"delivered": True},
    )
    db.add(art)
    await db.flush()
    rel = f"deliveries/{project.id}/{art.id}{ext}"
    dest = media_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(file), dest)
    else:
        shutil.copy2(file, dest)
    duration = await _probe_duration(dest)
    record = {
        "artifact_id": art.id,
        "source": source,
        "source_label": SOURCES.get(source, source),
        "file_name": Path(filename).name[:200],
        "size": size,
        "duration": duration,
        "note": (note or "").strip()[:500] or None,
        "at": datetime.now(UTC).isoformat(),
    }
    art.relative_path = rel
    art.status = "done"
    art.progress = {"stage": "已回传", "percent": 100, **record}
    content = dict(output.content or {})
    content["deliveries"] = [*(content.get("deliveries") or []), record][-20:]
    output.content = content
    if output.status != "rendering":
        output.status = "done"
    if not output.based_on_version:
        output.based_on_version = version
    await db.commit()
    await ps._feishu_stage(db, output.project_id)
    return {"delivery": record, "output": await ps.output_view(db, output.id)}


async def attach_from_url(
    db: AsyncSession, output_id: int, url: str, *, note: str | None = None, source: str = "agent"
) -> dict[str, Any]:
    name = url.split("?")[0].rstrip("/").split("/")[-1] or "video.mp4"
    tmp = await staging_path(output_id, name)
    total = 0
    try:
        client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=300))
        async with client, client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                raise ValidationError(f"下载失败：HTTP {resp.status_code}")
            with tmp.open("wb") as fh:
                async for chunk in resp.aiter_bytes(1 << 20):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValidationError("文件超过 4 GB")
                    fh.write(chunk)
        return await attach(db, output_id, tmp, filename=name, source=source, note=note, move=True)
    finally:
        tmp.unlink(missing_ok=True)


def bundle_brief(output_view: dict[str, Any], markdown: str) -> dict[str, Any]:
    return {
        "output_id": output_view["id"],
        "project_id": output_view["project_id"],
        "kind": output_view["kind"],
        "title": output_view["title"],
        "based_on_version": output_view["based_on_version"],
        "markdown": markdown,
        "deliver_with": "upload_output（path 为本机视频文件的绝对路径，或 url 为可下载地址）",
    }
