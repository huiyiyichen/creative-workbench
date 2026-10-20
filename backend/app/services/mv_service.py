"""音乐 MV 的音频与歌词（创作工作台设计 5.1 / 6.4）：上传音频、粘贴或上传 LRC，在歌词时间轴上校对。

* 音频存进项目素材目录（StudioAsset kind=audio，最新一条为准），时长用 ffprobe 读出，设定里的目标时长跟随音频。
* LRC 是歌词时间的唯一来源（AI 不改歌词）：解析成 draft.cues；分镜边界尽量落在歌词时间点上。
* 两者都会写一个新版本、换 draft_token，并取消定稿。
"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.studio import StudioAsset
from app.schemas.studio import StudioDraft
from app.services import project_service as ps
from app.services.studio_lrc import parse_lrc

SAFE_NAME = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")


def media_root() -> Path:
    from app.services.studio_media import MEDIA_ROOT

    return MEDIA_ROOT


async def probe(path: Path) -> float:
    from app.services.studio_media import probe_audio

    return await probe_audio(path)


def retime(draft: StudioDraft, duration: float) -> StudioDraft:
    """音频成为时间轴：总时长对齐音频；有歌词时分镜边界尽量取歌词时间点，否则均分。"""
    if not draft.shots:
        return draft
    total = max(5.0, float(duration))
    n = len(draft.shots)
    boundaries = [0.0]
    cue_times = sorted({c.time for c in draft.cues if 0 < c.time < total})
    if cue_times and len(cue_times) >= n - 1:
        step = len(cue_times) / n
        boundaries.extend(cue_times[max(0, min(len(cue_times) - 1, round(step * i) - 1))] for i in range(1, n))
        boundaries = sorted(set(boundaries))
    if len(boundaries) != n:
        each = round(total / n, 3)
        boundaries = [round(each * i, 3) for i in range(n)]
    boundaries.append(total)
    shots = [
        s.model_copy(update={"seconds": round(max(0.1, boundaries[i + 1] - boundaries[i]), 3)})
        for i, s in enumerate(draft.shots)
    ]
    fix = round(total - sum(s.seconds for s in shots), 3)
    shots[-1] = shots[-1].model_copy(update={"seconds": round(max(0.1, shots[-1].seconds + fix), 3)})
    return draft.model_copy(update={"shots": shots})


async def _audio(db: AsyncSession, project_id: int) -> StudioAsset | None:
    return (
        await db.execute(
            select(StudioAsset)
            .where(StudioAsset.project_id == project_id, StudioAsset.kind == "audio")
            .order_by(StudioAsset.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _audio_dict(a: StudioAsset | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {"id": a.id, "name": a.name, "duration": a.duration, "url": f"/projects/{a.project_id}/audio/file"}


async def audio_info(db: AsyncSession, project_id: int) -> dict[str, Any]:
    await ps.get_project(db, project_id)
    return {"audio": _audio_dict(await _audio(db, project_id))}


async def audio_path(db: AsyncSession, project_id: int) -> tuple[Path, str]:
    a = await _audio(db, project_id)
    if a is None:
        raise NotFoundError("音频", project_id)
    root = media_root().resolve()
    path = (root / a.relative_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise NotFoundError("音频文件", a.id)
    return path, a.name


async def _apply(db: AsyncSession, project, *, draft: StudioDraft, duration: float | None, reason: str) -> None:
    spec = deepcopy(project.spec or {})
    brief = dict(spec.get("brief") or {})
    brief["mode"] = "music_video"
    if duration:
        brief["duration_seconds"] = max(5, min(600, int(round(duration))))
    spec["brief"] = brief
    spec["draft"] = draft.model_dump(mode="json")
    project.spec = spec
    project.draft_token = ps._token()
    project.finalized_version = None
    if project.stage == "idea":
        project.stage = "draft"
    await ps._snapshot(db, project, reason)


async def add_audio(db: AsyncSession, project_id: int, filename: str, content: bytes) -> dict[str, Any]:
    from app.services.studio_media import AUDIO_EXTENSIONS, MAX_AUDIO_BYTES

    if not content:
        raise ValidationError("音频文件是空的")
    if len(content) > MAX_AUDIO_BYTES:
        raise ValidationError("音频文件不得超过 50 MB")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise ValidationError("只支持 MP3、WAV、M4A、OGG 和 FLAC")
    project = await ps.get_project(db, project_id, lock=True)
    if project.finalized_version:
        raise ps.conflict("finalized", "已定稿，点「继续修改」后才能换音频")
    digest = hashlib.sha256(content).hexdigest()
    safe = SAFE_NAME.sub("-", Path(filename).name)[:120] or f"audio{suffix}"
    relative = f"{project.id}/{digest[:16]}-{safe}"
    path = media_root() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    try:
        duration = await probe(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    draft = StudioDraft.model_validate((project.spec or {}).get("draft") or {})
    if draft.cues and any(c.time >= duration for c in draft.cues):
        draft = draft.model_copy(update={"cues": [c for c in draft.cues if c.time < duration]})
    await db.execute(delete(StudioAsset).where(StudioAsset.project_id == project.id, StudioAsset.kind == "audio"))
    asset = StudioAsset(
        project_id=project.id, kind="audio", name=safe, relative_path=relative, sha256=digest, duration=duration
    )
    db.add(asset)
    await _apply(db, project, draft=retime(draft, duration), duration=duration, reason="audio")
    await db.commit()
    return {"audio": _audio_dict(asset), "draft": await ps.draft_view(db, project.id)}


async def set_lrc(db: AsyncSession, project_id: int, text: str) -> dict[str, Any]:
    project = await ps.get_project(db, project_id, lock=True)
    if project.finalized_version:
        raise ps.conflict("finalized", "已定稿，点「继续修改」后才能改歌词")
    audio = await _audio(db, project.id)
    cues = parse_lrc(text, audio.duration if audio else None)
    draft = StudioDraft.model_validate((project.spec or {}).get("draft") or {}).model_copy(update={"cues": cues})
    duration = audio.duration if audio and audio.duration else None
    if duration:
        draft = retime(draft, duration)
    await _apply(db, project, draft=draft, duration=duration, reason="lrc")
    await db.commit()
    return await ps.draft_view(db, project.id)
