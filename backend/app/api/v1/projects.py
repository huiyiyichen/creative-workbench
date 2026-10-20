"""阶段 4 创作工作台接口：项目、来源、设定、文稿工作副本、版本、定稿、产出物、素材。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.models.user import User
from app.schemas.projects import (
    AssetAdd,
    BriefSave,
    DraftGenerate,
    DraftSave,
    FinalizeRequest,
    LrcBody,
    OutputCreate,
    OutputPatch,
    PipelineStart,
    PlatformRewrite,
    ProjectCreate,
    ProjectPatch,
    SourceAdd,
    SourceRole,
    SuggestionApply,
    SuggestionCreate,
    VersionCreate,
)
from app.services import (
    mv_service,
    output_service as out_svc,
    pipeline_service,
    platform_flow,
    project_service as svc,
    suggestion_service as sug_svc,
)

router = APIRouter(tags=["projects"], dependencies=[Depends(get_current_user)])


# ── 项目 ──
@router.get("/projects")
async def list_projects(
    stage: str | None = Query(None, pattern="^(idea|draft|outputs)$"),
    q: str | None = Query(None, max_length=100),
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_projects(db, stage=stage, q=q, archived=archived)


@router.post("/projects")
async def create_project(
    request: ProjectCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await svc.create_project(db, user.id, request)


@router.get("/projects/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.project_view(db, project_id)


@router.patch("/projects/{project_id}")
async def rename_project(project_id: int, request: ProjectPatch, db: AsyncSession = Depends(get_db)):
    return await svc.rename_project(db, project_id, request.title)


@router.post("/projects/{project_id}/archive")
async def archive_project(project_id: int, restore: bool = False, db: AsyncSession = Depends(get_db)):
    return await svc.archive_project(db, project_id, archived=not restore)


# ── 来源 ──
@router.get("/projects/{project_id}/sources")
async def list_sources(project_id: int, db: AsyncSession = Depends(get_db)):
    await svc.get_project(db, project_id)
    return {"items": await svc.list_sources(db, project_id)}


@router.post("/projects/{project_id}/sources")
async def add_source(project_id: int, request: SourceAdd, db: AsyncSession = Depends(get_db)):
    return await svc.add_source(db, project_id, request)


@router.patch("/projects/{project_id}/sources/{source_id}")
async def set_source_role(project_id: int, source_id: int, request: SourceRole, db: AsyncSession = Depends(get_db)):
    return await svc.set_source_role(db, project_id, source_id, request.role)


@router.delete("/projects/{project_id}/sources/{source_id}", status_code=204)
async def remove_source(project_id: int, source_id: int, db: AsyncSession = Depends(get_db)):
    await svc.remove_source(db, project_id, source_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/directions")
async def start_directions(project_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.start_directions(db, project_id)


# ── 设定与文稿 ──
@router.put("/projects/{project_id}/brief")
async def save_brief(project_id: int, request: BriefSave, db: AsyncSession = Depends(get_db)):
    return await svc.save_brief(db, project_id, request)


@router.get("/projects/{project_id}/draft")
async def get_draft(project_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.draft_view(db, project_id)


@router.put("/projects/{project_id}/draft")
async def save_draft(project_id: int, request: DraftSave, db: AsyncSession = Depends(get_db)):
    return await svc.save_draft(db, project_id, request)


@router.post("/projects/{project_id}/draft/generate")
async def generate_draft(project_id: int, request: DraftGenerate, db: AsyncSession = Depends(get_db)):
    return await svc.generate_draft(db, project_id, request.mode)


@router.post("/projects/{project_id}/platforms/rewrite")
async def rewrite_platforms(project_id: int, request: PlatformRewrite, db: AsyncSession = Depends(get_db)):
    """生成平台版本：启动平台改写流程（平台编辑按平台并行 → 规则校验），返回运行 id。"""
    return await platform_flow.start_platform_rewrite(db, project_id, list(request.kinds), request.output_ids)


@router.post("/outputs/{output_id}/deliveries")
async def upload_delivery(
    output_id: int,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """回传成片：上传外部 agent 做好的视频，挂到这个产出物上。"""
    from app.services import delivery_service

    tmp = await delivery_service.staging_path(output_id, file.filename or "")
    size = 0
    try:
        with tmp.open("wb") as fh:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > delivery_service.MAX_BYTES:
                    raise ValidationError("文件超过 4 GB")
                fh.write(chunk)
        return await delivery_service.attach(
            db, output_id, tmp, filename=file.filename or tmp.name, source="upload", note=note, move=True
        )
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/works")
async def list_works(
    q: str | None = None, kind: str | None = None, project: int | None = None, db: AsyncSession = Depends(get_db)
):
    """作品库：按项目归档的产出物（完成 / 已导出 / 已发布自动收录，草稿可手动加入）与旧成片。"""
    from app.services import works_service

    return await works_service.list_works(db, q=(q or "")[:100] or None, kind=kind, project_id=project)


@router.post("/outputs/{output_id}/works")
async def add_to_works(output_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import works_service

    return await works_service.set_in_works(db, output_id, True)


@router.delete("/outputs/{output_id}/works")
async def remove_from_works(output_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import works_service

    return await works_service.set_in_works(db, output_id, False)


@router.post("/projects/{project_id}/pipeline")
async def start_pipeline(project_id: int, request: PipelineStart, db: AsyncSession = Depends(get_db)):
    """一键全流程：选题研究 →〔选方向〕→ 成稿 →〔接受〕→〔定稿〕→ 讲解视频 + 平台改写。"""
    return await pipeline_service.start(
        db, project_id, outputs=list(request.outputs), choose_gate=request.choose_gate, accept_gate=request.accept_gate
    )


@router.post("/projects/{project_id}/pipeline/stop")
async def stop_pipeline(project_id: int, db: AsyncSession = Depends(get_db)):
    return await pipeline_service.stop(db, project_id)


@router.get("/projects/{project_id}/versions")
async def list_versions(project_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.list_versions(db, project_id)


@router.post("/projects/{project_id}/versions")
async def create_version(project_id: int, request: VersionCreate, db: AsyncSession = Depends(get_db)):
    return await svc.create_version(db, project_id, request.reason)


@router.get("/projects/{project_id}/versions/{version}")
async def get_version(project_id: int, version: int, db: AsyncSession = Depends(get_db)):
    return await svc.version_view(db, project_id, version)


@router.post("/projects/{project_id}/versions/{version}/restore")
async def restore_version(project_id: int, version: int, db: AsyncSession = Depends(get_db)):
    return await svc.restore_version(db, project_id, version)


@router.post("/projects/{project_id}/finalize")
async def finalize(project_id: int, request: FinalizeRequest, db: AsyncSession = Depends(get_db)):
    return await svc.finalize(db, project_id, request.version)


@router.post("/projects/{project_id}/unlock")
async def unlock(project_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.unlock(db, project_id)


# ── 产出物 ──
@router.get("/projects/{project_id}/outputs")
async def list_outputs(project_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.list_outputs(db, project_id)


@router.post("/projects/{project_id}/outputs")
async def create_output(project_id: int, request: OutputCreate, db: AsyncSession = Depends(get_db)):
    return await svc.create_output(db, project_id, request)


@router.get("/outputs/{output_id}")
async def get_output(output_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.output_view(db, output_id)


@router.patch("/outputs/{output_id}")
async def patch_output(output_id: int, request: OutputPatch, db: AsyncSession = Depends(get_db)):
    return await svc.patch_output(db, output_id, request)


@router.delete("/outputs/{output_id}", status_code=204)
async def delete_output(output_id: int, db: AsyncSession = Depends(get_db)):
    await svc.delete_output(db, output_id)
    return Response(status_code=204)


# ── 素材 ──
# ── 音乐 MV：音频与歌词 ──
@router.get("/projects/{project_id}/audio")
async def get_audio(project_id: int, db: AsyncSession = Depends(get_db)):
    return await mv_service.audio_info(db, project_id)


@router.post("/projects/{project_id}/audio")
async def post_audio(project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    from app.services.studio_media import MAX_AUDIO_BYTES

    return await mv_service.add_audio(db, project_id, file.filename or "", await file.read(MAX_AUDIO_BYTES + 1))


@router.get("/projects/{project_id}/audio/file")
async def audio_file(project_id: int, db: AsyncSession = Depends(get_db)):
    path, name = await mv_service.audio_path(db, project_id)
    return FileResponse(path, filename=name)


@router.put("/projects/{project_id}/lrc")
async def put_lrc(project_id: int, request: LrcBody, db: AsyncSession = Depends(get_db)):
    return await mv_service.set_lrc(db, project_id, request.text)


@router.get("/projects/{project_id}/assets")
async def list_assets(project_id: int, role: str | None = None, db: AsyncSession = Depends(get_db)):
    return await svc.list_assets(db, project_id, role)


@router.post("/projects/{project_id}/assets")
async def add_asset(project_id: int, request: AssetAdd, db: AsyncSession = Depends(get_db)):
    return await svc.add_asset(db, project_id, request)


@router.delete("/projects/{project_id}/assets/{asset_id}", status_code=204)
async def remove_asset(project_id: int, asset_id: int, db: AsyncSession = Depends(get_db)):
    await svc.remove_asset(db, project_id, asset_id)
    return Response(status_code=204)


# ── AI 建议 ──
@router.post("/projects/{project_id}/suggestions")
async def create_suggestion(project_id: int, request: SuggestionCreate, db: AsyncSession = Depends(get_db)):
    return await sug_svc.create_suggestion(
        db,
        project_id,
        scope=request.scope,
        instructions=request.instructions,
        quick=request.quick,
        n=request.n,
        draft_token=request.draft_token,
    )


@router.get("/projects/{project_id}/suggestions")
async def list_suggestions(project_id: int, db: AsyncSession = Depends(get_db)):
    return await sug_svc.list_suggestions(db, project_id)


@router.post("/suggestions/{suggestion_id}/apply")
async def apply_suggestion(suggestion_id: int, request: SuggestionApply, db: AsyncSession = Depends(get_db)):
    return await sug_svc.apply_suggestion(db, suggestion_id, request.op_ids)


@router.post("/suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: int, db: AsyncSession = Depends(get_db)):
    return await sug_svc.reject_suggestion(db, suggestion_id)


# ── 平台改写 / 导出 / 提示词包 ──
@router.post("/outputs/{output_id}/generate")
async def generate_output(output_id: int, db: AsyncSession = Depends(get_db)):
    return await out_svc.generate_platform(db, output_id)


@router.get("/outputs/{output_id}/check")
async def check_output(output_id: int, db: AsyncSession = Depends(get_db)):
    return await out_svc.check_output(db, output_id)


@router.get("/outputs/{output_id}/export")
async def export_output(
    output_id: int, format: str = Query("md", pattern="^(md|html)$"), db: AsyncSession = Depends(get_db)
):
    output = await svc.get_output(db, output_id)
    text, media = out_svc.platform_export(output.kind, output.content or {}, format)
    return Response(text, media_type=f"{media}; charset=utf-8")


@router.get("/outputs/{output_id}/bundle")
async def output_bundle(
    output_id: int, format: str = Query("md", pattern="^(md|zip)$"), db: AsyncSession = Depends(get_db)
):
    from urllib.parse import quote

    data, media, name = await out_svc.bundle(db, output_id, format)
    return Response(
        data, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"}
    )


# ── 制作（讲解视频 / MV 成片流程）──
@router.post("/outputs/{output_id}/render")
async def render_output(output_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import production_service

    return await production_service.start_render(db, output_id)


@router.get("/production/executors")
async def production_executors():
    from app.services import agent_adapters

    return {"items": agent_adapters.status()}
