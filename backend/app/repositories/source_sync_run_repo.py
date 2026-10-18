"""source_sync_runs / auto_actions 的数据访问。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from app.models.auto_action import AutoAction
from app.models.source_sync_run import SourceSyncRun, SyncRunStatus
from app.repositories.base import BaseRepository


class SourceSyncRunRepository(BaseRepository[SourceSyncRun]):
    model = SourceSyncRun

    async def add(self, run: SourceSyncRun) -> SourceSyncRun:
        self.db.add(run)
        await self.db.flush()
        return run

    async def recent_for_source(self, source_id: int, *, limit: int = 10) -> Sequence[SourceSyncRun]:
        stmt = (
            select(SourceSyncRun)
            .where(SourceSyncRun.source_id == source_id)
            .order_by(SourceSyncRun.started_at.desc(), SourceSyncRun.id.desc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def list_since(self, since: datetime, *, source_id: int | None = None) -> Sequence[SourceSyncRun]:
        stmt = select(SourceSyncRun).where(SourceSyncRun.started_at >= since)
        if source_id is not None:
            stmt = stmt.where(SourceSyncRun.source_id == source_id)
        stmt = stmt.order_by(SourceSyncRun.started_at.asc(), SourceSyncRun.id.asc())
        return (await self.db.execute(stmt)).scalars().all()

    async def productive_run_times(self, source_id: int, since: datetime) -> list[datetime]:
        """近一段时间内有新增的运行开始时间（升序），用于计算「平常间隔」。"""
        stmt = (
            select(SourceSyncRun.started_at)
            .where(
                SourceSyncRun.source_id == source_id,
                SourceSyncRun.started_at >= since,
                SourceSyncRun.new > 0,
            )
            .order_by(SourceSyncRun.started_at.asc())
        )
        return [row[0] for row in (await self.db.execute(stmt)).all()]

    async def last_success_at(self, source_id: int) -> datetime | None:
        stmt = select(func.max(SourceSyncRun.finished_at)).where(
            SourceSyncRun.source_id == source_id,
            SourceSyncRun.status.in_([SyncRunStatus.SUCCESS.value, SyncRunStatus.EMPTY.value]),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


class AutoActionRepository(BaseRepository[AutoAction]):
    model = AutoAction

    async def add(self, action: AutoAction) -> AutoAction:
        self.db.add(action)
        await self.db.flush()
        return action

    async def list_recent(self, *, limit: int = 50, include_undone: bool = True) -> Sequence[AutoAction]:
        stmt = select(AutoAction)
        if not include_undone:
            stmt = stmt.where(AutoAction.undone_at.is_(None))
        stmt = stmt.order_by(AutoAction.executed_at.desc(), AutoAction.id.desc()).limit(limit)
        return (await self.db.execute(stmt)).scalars().all()

    async def latest_open_for(self, target_type: str, target_id: str, action_type: str) -> AutoAction | None:
        stmt = (
            select(AutoAction)
            .where(
                AutoAction.target_type == target_type,
                AutoAction.target_id == target_id,
                AutoAction.action_type == action_type,
                AutoAction.undone_at.is_(None),
            )
            .order_by(AutoAction.executed_at.desc(), AutoAction.id.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
