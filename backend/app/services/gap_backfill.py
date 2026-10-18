"""空档补采（改造方案 3.7）。

启动时检查每个启用信源的上次成功时间；空档超过 2 个同步间隔（且至少 1 小时）：

* 订阅 / RSS：按发布时间往回翻页补到上次成功时间，最多 7 天 / 200 条；同步记录标记为补采。
* 热榜（榜单）：只有当时的快照，补不回来，写一条「缺失」记录（状态 skipped，带空档起止）。

补回的内容按发布日期归档（``attributed_date``），缺发布时间的按采集日期。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source, SourceKind, SourceType
from app.models.source_sync_run import SourceSyncRun, SyncRunStatus, SyncTrigger
from app.repositories.source_repo import SourceRepository
from app.repositories.source_sync_run_repo import SourceSyncRunRepository
from app.services.backfill_context import MAX_BACKFILL_DAYS, BackfillWindow, backfill_window

logger = logging.getLogger(__name__)

MIN_GAP = timedelta(hours=1)
_LIST_TYPES = {SourceType.DOUYIN_HOT, SourceType.ZHIHU}
LOCAL_FMT = "%m-%d %H:%M"


@dataclass
class Gap:
    source_id: int
    name: str
    last_success: datetime
    is_list: bool


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_list_source(source: Source) -> bool:
    if source.kind == SourceKind.LIST.value or source.source_type in _LIST_TYPES:
        return True
    return source.source_type == SourceType.PLATFORM and "/ranking/" in (source.url or "")


async def find_gaps(db: AsyncSession, *, now: datetime | None = None) -> list[Gap]:
    now = now or datetime.now(UTC)
    runs = SourceSyncRunRepository(db)
    gaps: list[Gap] = []
    for source in await SourceRepository(db).get_enabled_sources():
        if source.auto_paused_at is not None:
            continue
        last = await runs.last_success_at(source.id) or source.last_sync_at
        if last is None:
            continue  # 从没成功过：交给常规同步
        last = _aware(last)
        interval = timedelta(minutes=max(int(source.fetch_interval_minutes or 60), 5))
        if now - last > max(MIN_GAP, interval * 2):
            gaps.append(Gap(source.id, source.name, last, is_list_source(source)))
    return gaps


def _local(value: datetime) -> str:
    from zoneinfo import ZoneInfo

    return value.astimezone(ZoneInfo("Asia/Shanghai")).strftime(LOCAL_FMT)


async def record_missing_list(db: AsyncSession, gap: Gap, *, now: datetime) -> None:
    await SourceSyncRunRepository(db).add(
        SourceSyncRun(
            source_id=gap.source_id,
            trigger=SyncTrigger.STARTUP.value,
            started_at=now,
            finished_at=now,
            status=SyncRunStatus.SKIPPED.value,
            is_backfill=True,
            error_message=f"空档 {_local(gap.last_success)} – {_local(now)} 的榜单无法补回（平台只提供当时的快照）",
        )
    )


async def run_gap_backfill(
    session_factory: Callable[[], Any],
    *,
    sync: Callable[..., Awaitable[Any]],
    now: datetime | None = None,
) -> dict[str, int]:
    """``sync(db, source_id, trigger=..., is_backfill=True)`` 由调用方注入（调度器传 run_source_sync）。"""
    now = now or datetime.now(UTC)
    async with session_factory() as db:
        gaps = await find_gaps(db, now=now)
        for gap in gaps:
            if gap.is_list:
                await record_missing_list(db, gap, now=now)
        await db.commit()
    stats = {"gaps": len(gaps), "lists_missing": sum(g.is_list for g in gaps), "backfilled": 0, "failed": 0}
    for gap in gaps:
        if gap.is_list:
            continue
        since = max(gap.last_success, now - timedelta(days=MAX_BACKFILL_DAYS))
        try:
            async with session_factory() as db:
                with backfill_window(BackfillWindow(since=since)):
                    outcome = await sync(db, gap.source_id, trigger=SyncTrigger.STARTUP, is_backfill=True)
            if outcome is not None and getattr(outcome, "run", None) is not None and not outcome.failed:
                stats["backfilled"] += 1
            else:
                stats["failed"] += 1
        except Exception:
            logger.exception("gap backfill failed for source %s", gap.source_id)
            stats["failed"] += 1
    logger.info("gap backfill done: %s", stats)
    return stats
