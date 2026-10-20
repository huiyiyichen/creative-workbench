"""成片文件与配音设置（阶段 5 从旧 /studio/* 迁出）。

* ``/renders/{id}``：制作物（讲解视频 / MV 成片、回传的成片）的信息、预览、下载、动画工程源码。
* ``/voice/tts``：配音（千问 TTS）设置与试听，成片流程的配音节点读取它。
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories.project_repo import StudioRepo
from app.services import studio_service
from app.services.studio_tts import TtsSettings, save_tts_config, synthesize_speech, tts_config

router = APIRouter(tags=["renders"], dependencies=[Depends(get_current_user)])


async def _artifact(db: AsyncSession, artifact_id: int, user: User):
    artifact = await StudioRepo(db).artifact(artifact_id)
    if not artifact:
        raise NotFoundError("成片", artifact_id)
    await studio_service.get_project(db, artifact.project_id, user.id)
    return artifact


@router.get("/renders/{artifact_id}")
async def get_render(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return studio_service.artifact_dict(await _artifact(db, artifact_id, user))


@router.get("/renders/{artifact_id}/preview")
async def preview_render(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    path = studio_service.artifact_preview_file(await _artifact(db, artifact_id, user))
    if path is None:
        raise NotFoundError("成片预览", artifact_id)
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "video/mp4")


@router.get("/renders/{artifact_id}/download")
async def download_render(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    artifact = await _artifact(db, artifact_id, user)
    if artifact.status != "done" or not artifact.relative_path:
        raise NotFoundError("已完成的成片", artifact_id)
    root = studio_service.MEDIA_ROOT
    path = (root / artifact.relative_path).resolve()
    if not path.is_file() or not path.is_relative_to(root):
        raise NotFoundError("成片文件", artifact_id)
    media_type = (
        "application/zip" if path.suffix.lower() == ".zip" else mimetypes.guess_type(path.name)[0] or "video/mp4"
    )
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/renders/{artifact_id}/source")
async def download_render_source(
    artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    path = studio_service.artifact_source_file(await _artifact(db, artifact_id, user))
    if path is None:
        raise NotFoundError("动画工程", artifact_id)
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.get("/voice/tts")
async def get_tts_settings(db: AsyncSession = Depends(get_db)):
    return await tts_config(db)


@router.put("/voice/tts")
async def put_tts_settings(request: TtsSettings, db: AsyncSession = Depends(get_db)):
    return await save_tts_config(db, request)


@router.post("/voice/tts/preview")
async def preview_voice(db: AsyncSession = Depends(get_db)):
    config = await tts_config(db, with_secret=True)
    output = studio_service.MEDIA_ROOT / "voice-preview.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    await synthesize_speech("欢迎来到创意工作台。让每一个想法，都变成看得见、听得懂的作品。", config, output)
    return Response(output.read_bytes(), media_type="audio/wav")
