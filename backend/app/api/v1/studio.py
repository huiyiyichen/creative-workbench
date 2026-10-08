from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import async_session, get_db
from app.core.exceptions import NotFoundError
from app.core.task_registry import track_background_task
from app.models.user import User
from app.repositories.studio_repo import StudioRepo
from app.schemas.studio import CreateProject, GenerateDraft, SaveProject, VersionAction
from app.services.studio_catalog import catalog_for_user
from app.services.studio_media import MAX_AUDIO_BYTES, MEDIA_ROOT
from app.services.studio_service import (
    add_audio,
    add_lrc,
    artifact_dict,
    artifact_preview_file,
    artifact_source_file,
    build_prompt,
    create_project,
    finalize_project,
    generate_project_draft,
    get_project,
    production_jobs,
    project_view,
    queue_harness_production,
    queue_render,
    render_artifact,
    revision_view,
    run_harness_production,
    save_project,
)
from app.services.studio_tts import TtsSettings, save_tts_config, synthesize_speech, tts_config

router = APIRouter(prefix="/studio", tags=["studio"], dependencies=[Depends(get_current_user)])


@router.get("/tts")
async def get_tts_settings(db: AsyncSession = Depends(get_db)):
    return await tts_config(db)


@router.put("/tts")
async def put_tts_settings(request: TtsSettings, db: AsyncSession = Depends(get_db)):
    return await save_tts_config(db, request)


@router.post("/tts/preview")
async def preview_voice(db: AsyncSession = Depends(get_db)):
    config = await tts_config(db, with_secret=True)
    output = MEDIA_ROOT / "voice-preview.wav"
    await synthesize_speech("欢迎来到创意工作台。让每一个想法，都变成看得见、听得懂的作品。", config, output)
    return Response(output.read_bytes(), media_type="audio/wav")


@router.get("/catalog")
async def get_catalog(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await catalog_for_user(db, user.id)


@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    repo = StudioRepo(db)
    rows = await repo.list(user.id)
    return {"items": [await project_view(db, row.id, user.id) for row in rows], "total": len(rows)}


@router.get("/jobs")
async def list_production_jobs(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await production_jobs(db, user.id)


@router.get("/projects/{project_id}/revisions/{version}")
async def get_revision(
    project_id: int, version: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await revision_view(db, user.id, project_id, version)


@router.post("/projects")
async def post_project(req: CreateProject, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await create_project(db, user.id, req)


@router.get("/projects/{project_id}")
async def get_project_view(project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await project_view(db, project_id, user.id)


@router.put("/projects/{project_id}")
async def put_project(
    project_id: int, req: SaveProject, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await save_project(db, user.id, project_id, req)


@router.post("/projects/{project_id}/draft")
async def post_draft(
    project_id: int, req: GenerateDraft, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await generate_project_draft(db, user.id, project_id, req)


@router.get("/projects/{project_id}/production-prompt")
async def get_production_prompt(project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await build_prompt(db, user.id, project_id)


@router.post("/projects/{project_id}/audio")
async def post_audio(
    project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await add_audio(db, user.id, project_id, file.filename or "", await file.read(MAX_AUDIO_BYTES + 1))


@router.post("/projects/{project_id}/lrc")
async def post_lrc(
    project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    payload = await file.read()
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        from app.core.exceptions import ValidationError

        raise ValidationError("LRC 必须使用 UTF-8 编码") from None
    return await add_lrc(db, user.id, project_id, text)


@router.post("/projects/{project_id}/finalize")
async def post_finalize(
    project_id: int, req: VersionAction, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await finalize_project(db, user.id, project_id, req.expected_version)


@router.post("/projects/{project_id}/render")
async def post_render(
    project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    artifact = await queue_render(db, user.id, project_id)
    worker = run_harness_production(artifact.id) if artifact.kind == "remotion_video" else _render_in_new_session(artifact.id)
    track_background_task(worker, name=f"studio-render-{artifact.id}")
    return {"artifact_id": artifact.id, "status": artifact.status}


@router.post("/projects/{project_id}/harness-production")
async def post_harness_production(
    project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    artifact = await queue_harness_production(db, user.id, project_id)
    track_background_task(
        run_harness_production(artifact.id),
        name=f"studio-harness-production-{artifact.id}",
    )
    return {"artifact_id": artifact.id, "status": artifact.status, "kind": artifact.kind}


async def _render_in_new_session(artifact_id: int):
    async with async_session() as db:
        await render_artifact(db, artifact_id)


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    artifact = await StudioRepo(db).artifact(artifact_id)
    if not artifact:
        raise NotFoundError("作品", artifact_id)
    await get_project(db, artifact.project_id, user.id)
    return artifact_dict(artifact)


@router.get("/artifacts/{artifact_id}/preview")
async def preview_artifact(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    artifact = await StudioRepo(db).artifact(artifact_id)
    if not artifact:
        raise NotFoundError("作品", artifact_id)
    await get_project(db, artifact.project_id, user.id)
    path = artifact_preview_file(artifact)
    if path is None:
        raise NotFoundError("成片预览", artifact_id)
    return FileResponse(path, media_type="video/mp4")


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    artifact = await StudioRepo(db).artifact(artifact_id)
    if not artifact:
        raise NotFoundError("作品", artifact_id)
    await get_project(db, artifact.project_id, user.id)
    if artifact.status != "done" or not artifact.relative_path:
        raise NotFoundError("已完成作品", artifact_id)
    path = (MEDIA_ROOT / artifact.relative_path).resolve()
    if not path.is_file() or not path.is_relative_to(MEDIA_ROOT):
        raise NotFoundError("作品文件", artifact_id)
    media_type = "application/zip" if path.suffix.lower() == ".zip" else "video/mp4"
    return FileResponse(path, media_type=media_type, filename=Path(path).name)


@router.get("/artifacts/{artifact_id}/source")
async def download_source(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    artifact = await StudioRepo(db).artifact(artifact_id)
    if not artifact:
        raise NotFoundError("作品", artifact_id)
    await get_project(db, artifact.project_id, user.id)
    path = artifact_source_file(artifact)
    if path is None:
        raise NotFoundError("动画工程", artifact_id)
    return FileResponse(path, media_type="application/zip", filename=path.name)
