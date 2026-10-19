"""启动时补跑错过的日报 / 周刊 / 月刊（第 13 节 #11）。

调度器的 cron 任务在应用没开时会被跳过（``misfire_grace_time=120``），
那天、那周就没有报告。启动后检查最近的周期，只为「完全没有记录」且有采集数据的周期补跑；
已有记录（包括失败的）不重复生成，失败的由用户在报告页手动重试。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.report_catchup_repo import ReportCatchupRepository

logger = logging.getLogger(__name__)

DAILY_LOOKBACK_DAYS = 7
WEEKLY_LOOKBACK = 4
MONTHLY_LOOKBACK = 2


def missing_periods(today: date) -> tuple[list[date], list[date], list[date]]:
    """返回候选周期：日报（前 1..7 天）、周刊参考日、月刊参考日。

    周刊 / 月刊函数生成的是「参考日的上一周 / 上一月」，所以这里给参考日。
    """
    days = [today - timedelta(days=i) for i in range(1, DAILY_LOOKBACK_DAYS + 1)]
    this_monday = today - timedelta(days=today.weekday())
    week_refs = [this_monday - timedelta(weeks=i) for i in range(WEEKLY_LOOKBACK)]
    month_refs: list[date] = []
    ref = date(today.year, today.month, 1)
    for _ in range(MONTHLY_LOOKBACK):
        month_refs.append(ref)
        ref = date(ref.year - 1, 12, 1) if ref.month == 1 else date(ref.year, ref.month - 1, 1)
    return days, week_refs, month_refs


def _week_key_for_ref(ref: date) -> str:
    prev = ref - timedelta(days=7)
    iso = prev.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _month_key_for_ref(ref: date) -> str:
    prev = date(ref.year - 1, 12, 1) if ref.month == 1 else date(ref.year, ref.month - 1, 1)
    return f"{prev.year}-{prev.month:02d}"


async def catch_up_reports(db: AsyncSession, *, today: date | None = None) -> dict[str, list[str]]:
    from app.services.daily_report import _local_today, generate_daily_report
    from app.services.monthly_digest import generate_monthly_digest
    from app.services.weekly_digest import generate_weekly_digest

    today = today or _local_today()
    days, week_refs, month_refs = missing_periods(today)
    repo = ReportCatchupRepository(db)
    done: dict[str, list[str]] = {"daily": [], "weekly": [], "monthly": []}

    from app.services.period_reports import has_collected_data

    existing_days = await repo.existing_final_daily_dates([d.isoformat() for d in days])
    for d in sorted(days):
        if d.isoformat() in existing_days:
            continue
        # 没有采集数据的日期不生成日报，归档日历里标「未采集」（5.4）
        if not await has_collected_data(db, d):
            done.setdefault("uncollected", []).append(d.isoformat())
            continue
        try:
            await generate_daily_report(db, target_date=d, edition="final")
            done["daily"].append(d.isoformat())
        except Exception:
            logger.warning("report catch-up: daily %s failed", d, exc_info=True)
            await db.rollback()

    week_keys = {_week_key_for_ref(r): r for r in week_refs}
    existing_weeks = await repo.existing_week_keys(list(week_keys))
    for key, ref in sorted(week_keys.items()):
        if key in existing_weeks:
            continue
        try:
            await generate_weekly_digest(db, reference_date=ref)
            done["weekly"].append(key)
        except Exception:
            logger.warning("report catch-up: weekly %s failed", key, exc_info=True)
            await db.rollback()

    month_keys = {_month_key_for_ref(r): r for r in month_refs}
    existing_months = await repo.existing_month_keys(list(month_keys))
    for key, ref in sorted(month_keys.items()):
        if key in existing_months:
            continue
        try:
            await generate_monthly_digest(db, reference_date=ref)
            done["monthly"].append(key)
        except Exception:
            logger.warning("report catch-up: monthly %s failed", key, exc_info=True)
            await db.rollback()

    if any(done.values()):
        logger.info("report catch-up generated: %s", done)
    return done
