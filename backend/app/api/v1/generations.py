"""生成服务与生图（改造方案第 8 节、创作工作台设计 6.5）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services import generation_service as gen

router = APIRouter(tags=["generations"], dependencies=[Depends(get_current_user)])


class ServiceBody(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    kind: Literal["image", "video", "music"] | None = None
    api_format: Literal["openai_images", "openai_videos"] | None = None
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=100)
    capabilities: dict | None = None
    unit_price: float | None = Field(default=None, ge=0, le=100)
    daily_limit: float | None = Field(default=None, ge=0, le=10000)
    enabled: bool | None = None
    is_default: bool | None = None


class ImageBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    ref_item_ids: list[int] = Field(default_factory=list, max_length=8)
    aspect: Literal["1:1", "3:4", "4:3", "16:9", "9:16"] | None = None
    n: int = Field(default=4, ge=1, le=8)
    service_id: int | None = None
    project_id: int | None = None
    output_id: int | None = None
    target: dict | None = None
    parent_job_id: int | None = None
    parent_index: int | None = None


class VideoBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    first_frame_item_id: int | None = None
    duration: int = Field(default=5, ge=1, le=60)
    aspect: Literal["16:9", "9:16", "1:1"] | None = None
    service_id: int | None = None
    project_id: int | None = None
    output_id: int | None = None
    target: dict | None = None


class KeepBody(BaseModel):
    indexes: list[int] = Field(min_length=1, max_length=8)
    role: Literal["moodboard", "illustration", "cover", "keyframe", "bgm"] | None = None
    target: dict | None = None


class PromptBody(BaseModel):
    target: dict | None = None
    style_id: str | None = None
    ref_item_ids: list[int] = Field(default_factory=list, max_length=8)


@router.get("/generation/services")
async def list_services(kind: str | None = None, db: AsyncSession = Depends(get_db)):
    return {"items": await gen.list_services(db, kind)}


@router.post("/generation/services")
async def create_service(body: ServiceBody, db: AsyncSession = Depends(get_db)):
    return await gen.save_service(db, body.model_dump(exclude_unset=True))


@router.patch("/generation/services/{service_id}")
async def update_service(service_id: int, body: ServiceBody, db: AsyncSession = Depends(get_db)):
    return await gen.save_service(db, body.model_dump(exclude_unset=True), service_id)


@router.delete("/generation/services/{service_id}", status_code=204)
async def delete_service(service_id: int, db: AsyncSession = Depends(get_db)):
    await gen.delete_service(db, service_id)


@router.post("/generation/services/{service_id}/test")
async def test_service(service_id: int, db: AsyncSession = Depends(get_db)):
    return await gen.test_service(db, service_id)


@router.post("/generations/images")
async def create_images(body: ImageBody, db: AsyncSession = Depends(get_db)):
    job = await gen.create_job(db, **body.model_dump())
    return gen.job_dict(job)


@router.post("/generations/videos")
async def create_video(body: VideoBody, db: AsyncSession = Depends(get_db)):
    """视频生成：异步任务，进任务中心；完成后可存入并使用。"""
    from app.services import video_generation

    job = await video_generation.create_video_job(db, **body.model_dump())
    return gen.job_dict(job)


@router.get("/generations")
async def list_jobs(project_id: int | None = None, db: AsyncSession = Depends(get_db)):
    return {"items": await gen.list_jobs(db, project_id)}


@router.get("/generations/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    return await gen.get_job(db, job_id)


@router.get("/generations/{job_id}/files/{index}")
async def job_file(job_id: int, index: int, db: AsyncSession = Depends(get_db)):
    path = await gen.file_for(db, job_id, index)
    return FileResponse(path, media_type="video/mp4" if path.suffix.lower() == ".mp4" else "image/png")


@router.post("/generations/{job_id}/keep")
async def keep(job_id: int, body: KeepBody, db: AsyncSession = Depends(get_db)):
    return await gen.keep(db, job_id, body.indexes, role=body.role, target=body.target)


@router.post("/projects/{project_id}/image-prompt")
async def image_prompt(project_id: int, body: PromptBody, db: AsyncSession = Depends(get_db)):
    return await gen.draft_prompt(
        db, project_id=project_id, target=body.target, style_id=body.style_id, ref_item_ids=body.ref_item_ids
    )


@router.post("/generations/image-prompt")
async def image_prompt_free(body: PromptBody, db: AsyncSession = Depends(get_db)):
    return await gen.draft_prompt(
        db, project_id=None, target=body.target, style_id=body.style_id, ref_item_ids=body.ref_item_ids
    )
