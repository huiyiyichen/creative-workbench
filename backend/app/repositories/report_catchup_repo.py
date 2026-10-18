"""报告补跑需要的存在性查询。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.monthly_digest import MonthlyDigest
from app.models.weekly_digest import WeeklyDigest


class ReportCatchupRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def existing_final_daily_dates(self, dates: list[str]) -> set[str]:
        if not dates:
            return set()
        stmt = select(DailyReport.report_date).where(
            DailyReport.report_date.in_(dates),
            DailyReport.edition == "final",
            DailyReport.owner_user_id.is_(None),
        )
        return {row[0] for row in (await self.db.execute(stmt)).all()}

    async def existing_week_keys(self, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        stmt = select(WeeklyDigest.week_key).where(WeeklyDigest.week_key.in_(keys))
        return {row[0] for row in (await self.db.execute(stmt)).all()}

    async def existing_month_keys(self, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        stmt = select(MonthlyDigest.month_key).where(MonthlyDigest.month_key.in_(keys))
        return {row[0] for row in (await self.db.execute(stmt)).all()}
