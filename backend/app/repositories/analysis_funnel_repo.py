"""分析漏斗（改造方案 4.1 / 4.2）的数据访问：快速判断候选、预算花费。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentStatus
from app.models.llm_model import LlmCallLog

# 计入分析预算的模型调用场景
ANALYSIS_SCENES = ("content_analysis", "content_prescreen", "quick_judge")


class AnalysisFunnelRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def spent_since(self, since: datetime, scenes: Sequence[str] = ANALYSIS_SCENES) -> float:
        stmt = select(func.coalesce(func.sum(LlmCallLog.total_cost), 0.0)).where(
            LlmCallLog.created_at >= since, LlmCallLog.scene.in_(list(scenes))
        )
        return float((await self.db.execute(stmt)).scalar() or 0.0)

    async def quick_candidates(self, *, threshold: float, since: datetime, limit: int) -> Sequence[ContentItem]:
        """待快速判断：未判断、未跳过、初筛过线、排队未超期，按初筛分从高到低。"""
        stmt = (
            select(ContentItem)
            .where(
                ContentItem.status == ContentStatus.PENDING,
                ContentItem.skip_analysis.is_(False),
                ContentItem.full_eligible.is_(None),
                ContentItem.triage_score >= threshold,
                ContentItem.crawled_at >= since,
            )
            .order_by(ContentItem.triage_score.desc(), ContentItem.crawled_at.desc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def count_quick_backlog(self, *, threshold: float, since: datetime) -> int:
        stmt = select(func.count(ContentItem.id)).where(
            ContentItem.status == ContentStatus.PENDING,
            ContentItem.skip_analysis.is_(False),
            ContentItem.full_eligible.is_(None),
            ContentItem.triage_score >= threshold,
            ContentItem.crawled_at >= since,
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def mark_untriaged_eligible(self, *, since: datetime, limit: int) -> int:
        """历史数据没有初筛分时：直接放行到完整分析，避免永远卡在漏斗外。"""
        ids = (
            (
                await self.db.execute(
                    select(ContentItem.id)
                    .where(
                        ContentItem.status == ContentStatus.PENDING,
                        ContentItem.skip_analysis.is_(False),
                        ContentItem.full_eligible.is_(None),
                        ContentItem.triage_score.is_(None),
                        ContentItem.crawled_at >= since,
                    )
                    .order_by(ContentItem.crawled_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            return 0
        await self.db.execute(update(ContentItem).where(ContentItem.id.in_(ids)).values(full_eligible=True))
        return len(ids)
