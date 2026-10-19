"""报告（5.4）：归档日历、搜索、空档回看与任意时间段、完整度、前后连贯。

日报 / 周刊 / 月刊的生成与读取沿用 daily_reports / weekly_digests / monthly_digests 接口。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services.period_reports import (
    archive_calendar,
    daily_continuity,
    detect_and_generate_gap,
    generate_period_report,
    get_period_report,
    list_period_reports,
    period_view,
    search_reports,
)

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


class RangeBody(BaseModel):
    start_date: date
    end_date: date


@router.get("/calendar")
async def get_calendar(
    year: int = Query(..., ge=2020, le=2100), month: int = Query(..., ge=1, le=12), db: AsyncSession = Depends(get_db)
):
    return await archive_calendar(db, year, month)


@router.get("/search")
async def get_search(q: str = Query(..., min_length=1, max_length=100), db: AsyncSession = Depends(get_db)):
    return {"items": await search_reports(db, q)}


@router.get("/periods")
async def get_periods(kind: str | None = Query(None, pattern="^(gap|range)$"), db: AsyncSession = Depends(get_db)):
    return {"items": await list_period_reports(db, kind)}


@router.post("/periods")
async def post_period(body: RangeBody, db: AsyncSession = Depends(get_db)):
    try:
        report = await generate_period_report(db, "range", body.start_date, body.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return period_view(report)


@router.get("/periods/{report_id}")
async def get_period(report_id: int, db: AsyncSession = Depends(get_db)):
    report = await get_period_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.post("/periods/{report_id}/regenerate")
async def post_regenerate(report_id: int, db: AsyncSession = Depends(get_db)):
    """数据补齐后重新生成，旧版本保留。"""
    current = await get_period_report(db, report_id)
    if current is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    report = await generate_period_report(
        db, current["kind"], date.fromisoformat(current["start_date"]), date.fromisoformat(current["end_date"])
    )
    return period_view(report)


@router.post("/gaps/detect")
async def post_detect_gap(db: AsyncSession = Depends(get_db)):
    report = await detect_and_generate_gap(db)
    return {"generated": period_view(report) if report else None}


@router.get("/daily/{report_date}/continuity")
async def get_daily_continuity(report_date: date, db: AsyncSession = Depends(get_db)):
    result = await daily_continuity(db, report_date.isoformat())
    if result is None:
        raise HTTPException(status_code=404, detail="当天没有已完成的日报")
    return result
