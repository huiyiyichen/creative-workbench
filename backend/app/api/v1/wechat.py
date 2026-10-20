"""公众号草稿箱：设置、测试连接、把公众号版推到草稿箱。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services import wechat_mp_service as svc

router = APIRouter(tags=["wechat"], dependencies=[Depends(get_current_user)])


class WechatSettingsBody(BaseModel):
    app_id: str | None = Field(default=None, max_length=64)
    app_secret: str | None = Field(default=None, max_length=128)
    author: str | None = Field(default=None, max_length=16)
    source_url: str | None = Field(default=None, max_length=500)
    open_comment: bool | None = None


@router.get("/wechat/settings")
async def wechat_settings(db: AsyncSession = Depends(get_db)):
    return await svc.get_settings(db)


@router.put("/wechat/settings")
async def save_wechat_settings(body: WechatSettingsBody, db: AsyncSession = Depends(get_db)):
    return await svc.save_settings(db, body.model_dump())


@router.post("/wechat/test")
async def wechat_test(db: AsyncSession = Depends(get_db)):
    return await svc.test_connection(db)


@router.post("/outputs/{output_id}/wechat-draft")
async def push_wechat_draft(output_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.push_draft(db, output_id)
