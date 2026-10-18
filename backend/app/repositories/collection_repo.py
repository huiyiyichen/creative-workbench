"""采集页（改造方案 3.8）需要的聚合查询。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentStatus
from app.models.llm_model import LlmCallLog
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun


class CollectionStatsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_sources(self) -> Sequence[Source]:
        stmt = select(Source).where(Source.hidden.is_(False)).order_by(Source.sort_order.asc(), Source.id.asc())
        return (await self.db.execute(stmt)).scalars().all()

    async def runs_since(self, since: datetime) -> Sequence[SourceSyncRun]:
        stmt = (
            select(SourceSyncRun)
            .where(SourceSyncRun.started_at >= since)
            .order_by(SourceSyncRun.started_at.asc(), SourceSyncRun.id.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def count_crawled_between(self, start: datetime, end: datetime) -> int:
        stmt = select(func.count(ContentItem.id)).where(ContentItem.crawled_at >= start, ContentItem.crawled_at < end)
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def count_pending_analysis(self) -> int:
        stmt = select(func.count(ContentItem.id)).where(
            ContentItem.status.in_([ContentStatus.PENDING, ContentStatus.ANALYZING]),
            ContentItem.skip_analysis.is_(False),
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def status_counts_since(self, since: datetime) -> dict[str, int]:
        stmt = (
            select(ContentItem.status, func.count(ContentItem.id))
            .where(ContentItem.crawled_at >= since)
            .group_by(ContentItem.status)
        )
        return {str(getattr(k, "value", k)): int(v) for k, v in (await self.db.execute(stmt)).all()}

    async def funnel_counts_since(self, since: datetime, *, triage_threshold: float) -> dict[str, int]:
        """分析漏斗各层数量（改造方案 4.1）。精选 = 完整分析后推荐等级为强烈建议写 / 适合蹭热点 / 适合深挖。"""
        from sqlalchemy import case

        from app.models.analysis import AiAnalysis
        from app.services.recommendation_level import LEVEL_DEEP_DIVE, LEVEL_HOT_RIDE, LEVEL_STRONG_WRITE

        base = (ContentItem.crawled_at >= since) & (ContentItem.skip_analysis.is_(False))
        stmt = select(
            func.count(case((ContentItem.triage_score >= triage_threshold, 1))),
            func.count(case((ContentItem.quick_result.is_not(None), 1))),
            func.count(case((ContentItem.full_eligible.is_(True), 1))),
            func.count(case((ContentItem.analysis_level == "full", 1))),
        ).where(base)
        triaged, quick, quick_pass, full = (await self.db.execute(stmt)).one()
        picked_stmt = (
            select(func.count(func.distinct(AiAnalysis.content_id)))
            .join(ContentItem, ContentItem.id == AiAnalysis.content_id)
            .where(base, AiAnalysis.recommend_level.in_([LEVEL_STRONG_WRITE, LEVEL_HOT_RIDE, LEVEL_DEEP_DIVE]))
        )
        picked = int((await self.db.execute(picked_stmt)).scalar() or 0)
        return {
            "triaged": int(triaged),
            "quick": int(quick),
            "quick_pass": int(quick_pass),
            "full": int(full),
            "picked": picked,
        }

    async def skip_reason_counts_since(self, since: datetime) -> dict[str, int]:
        stmt = (
            select(ContentItem.skip_reason, func.count(ContentItem.id))
            .where(ContentItem.crawled_at >= since, ContentItem.skip_analysis.is_(True))
            .group_by(ContentItem.skip_reason)
        )
        return {str(k or "other"): int(v) for k, v in (await self.db.execute(stmt)).all()}

    async def llm_cost_between(self, start: datetime, end: datetime) -> float | None:
        """模型花费合计；没有任何调用记录时返回 None（缺失保持空值）。"""
        stmt = select(func.count(LlmCallLog.id), func.sum(LlmCallLog.total_cost)).where(
            LlmCallLog.created_at >= start, LlmCallLog.created_at < end
        )
        count, total = (await self.db.execute(stmt)).one()
        if not count:
            return None
        return float(total or 0.0)
