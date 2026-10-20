"""发布排期、发布日历、发布后数据回收与效果汇总。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services import publishing_service as svc

router = APIRouter(tags=["publishing"], dependencies=[Depends(get_current_user)])


class ScheduleBody(BaseModel):
    at: datetime | None = None
    platform: str | None = Field(default=None, max_length=40)
    note: str = Field(default="", max_length=200)


@router.put("/outputs/{output_id}/schedule")
async def put_schedule(output_id: int, body: ScheduleBody, db: AsyncSession = Depends(get_db)):
    return await svc.set_schedule(db, output_id, at=body.at, platform=body.platform, note=body.note)


@router.post("/outputs/{output_id}/metrics/refresh")
async def refresh_output_metrics(output_id: int, db: AsyncSession = Depends(get_db)):
    return await svc.refresh_metrics(db, output_id)


@router.get("/outputs/{output_id}/metrics")
async def output_metrics(output_id: int, db: AsyncSession = Depends(get_db)):
    return {"series": await svc.metric_series(db, output_id)}


@router.get("/publishing/calendar")
async def publishing_calendar(
    start: datetime = Query(...), end: datetime = Query(...), db: AsyncSession = Depends(get_db)
):
    return await svc.calendar(db, start, end)


@router.get("/publishing/performance")
async def publishing_performance(db: AsyncSession = Depends(get_db)):
    return await svc.performance(db)
