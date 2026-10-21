"""飞书多维表格（改造方案 10.2）：设置、测试连接、记入飞书、查看 / 重试同步记录。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services import feishu_service

router = APIRouter(prefix="/feishu", tags=["feishu"], dependencies=[Depends(get_current_user)])


class SettingsBody(BaseModel):
    app_id: str | None = Field(default=None, max_length=100)
    app_secret: str | None = Field(default=None, max_length=200)
    table_url: str | None = Field(default=None, max_length=1000)
    field_map: dict[str, str] | None = None
    auto_on_worth: bool | None = None
    auto_on_project: bool | None = None


class RecordBody(BaseModel):
    object_type: Literal["content", "project"]
    object_id: int


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    return await feishu_service.get_settings(db)


@router.put("/settings")
async def put_settings(body: SettingsBody, db: AsyncSession = Depends(get_db)):
    return await feishu_service.save_settings(db, body.model_dump(exclude_unset=True))


@router.post("/test")
async def test_connection(db: AsyncSession = Depends(get_db)):
    return await feishu_service.test_connection(db)


@router.post("/setup-columns")
async def setup_columns(db: AsyncSession = Depends(get_db)):
    """按字段映射在表格里建好缺的列。"""
    return await feishu_service.setup_columns(db)


@router.post("/records")
async def record(body: RecordBody, db: AsyncSession = Depends(get_db)):
    """记入飞书：没写过就新建记录，写过就更新。"""
    return await feishu_service.sync(db, body.object_type, body.object_id)


@router.get("/records")
async def get_record(object_type: Literal["content", "project"], object_id: int, db: AsyncSession = Depends(get_db)):
    return {"record": await feishu_service.get_record(db, object_type, object_id)}


@router.post("/records/{record_id}/retry")
async def retry(record_id: int, db: AsyncSession = Depends(get_db)):
    return await feishu_service.retry(db, record_id)
