"""采集页 API（改造方案 3.8 / 3.9）。

单用户本地应用：信源不分系统 / 个人，这里的动作对所有信源一视同仁。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.source_sync_run import SyncTrigger
from app.repositories.source_repo import SourceRepository
from app.services.collection_service import (
    build_funnel,
    build_health,
    build_overview,
    is_collection_paused,
    list_auto_actions,
    set_collection_paused,
)
from app.services.content_pipeline import ingest_from_source
from app.services.source_sync_service import AutoActionUndoError, run_source_sync, undo_auto_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/collection", tags=["collection"], dependencies=[Depends(get_current_user)])


@router.get("/overview")
async def collection_overview(db: AsyncSession = Depends(get_db)):
    return await build_overview(db)


@router.get("/health")
async def collection_health(db: AsyncSession = Depends(get_db)):
    return {"sources": await build_health(db)}


@router.get("/funnel")
async def collection_funnel(days: int = Query(7, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    return await build_funnel(db, days=days)


@router.get("/auto-actions")
async def collection_auto_actions(limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)):
    return {"items": await list_auto_actions(db, limit=limit)}


@router.post("/auto-actions/{action_id}/undo")
async def collection_undo_auto_action(action_id: int, db: AsyncSession = Depends(get_db)):
    try:
        action = await undo_auto_action(db, action_id)
    except AutoActionUndoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return {"id": action.id, "undone_at": action.undone_at}


class PauseRequest(BaseModel):
    paused: bool


@router.get("/pause")
async def collection_pause_state(db: AsyncSession = Depends(get_db)):
    return {"paused": await is_collection_paused(db)}


@router.put("/pause")
async def collection_set_pause(body: PauseRequest, db: AsyncSession = Depends(get_db)):
    """托盘「暂停采集」与采集页共用的全局开关；手动同步不受影响。"""
    return {"paused": await set_collection_paused(db, body.paused)}


@router.post("/sources/{source_id}/sync")
async def collection_sync_source(source_id: int, db: AsyncSession = Depends(get_db)):
    outcome = await run_source_sync(
        db,
        source_id,
        trigger=SyncTrigger.MANUAL,
        lease_seconds=int(settings.SOURCE_SYNC_TIMEOUT_SECONDS),
        ingest=ingest_from_source,
    )
    if outcome.run is None:
        if outcome.skipped_reason == "disabled":
            raise HTTPException(status_code=409, detail="信源已停用")
        raise HTTPException(status_code=409, detail="信源正在同步中，请稍后再试")
    if not outcome.failed:
        from app._post_sync_pipeline import _request_post_sync_pipeline

        _request_post_sync_pipeline(outcome.stats)
    run = outcome.run
    return {
        "status": run.status,
        "fetched": run.fetched,
        "new": run.new,
        "duplicates": run.duplicates,
        "error_kind": run.error_kind,
        "error_message": run.error_message,
    }


class SourceScheduleUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=7 * 24 * 60)


@router.patch("/sources/{source_id}")
async def collection_update_source(
    source_id: int, body: SourceScheduleUpdate, db: AsyncSession = Depends(get_db)
):
    repo = SourceRepository(db)
    source = await repo.get_by_id(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="信源不存在")
    if body.enabled is not None:
        source.enabled = body.enabled
    if body.interval_minutes is not None:
        source.fetch_interval_minutes = body.interval_minutes
        source.base_interval_minutes = None  # 手动改间隔即结束限流退避
    await db.commit()
    return {"id": source.id, "enabled": source.enabled, "interval_minutes": source.fetch_interval_minutes}
