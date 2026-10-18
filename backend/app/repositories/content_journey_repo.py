"""内容经历与指标观测的数据访问。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_observation import ContentJourney, ContentMetricObservation


class ContentJourneyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, entry: ContentJourney) -> ContentJourney:
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_for_content(self, content_id: int) -> Sequence[ContentJourney]:
        stmt = (
            select(ContentJourney)
            .where(ContentJourney.content_id == content_id)
            .order_by(ContentJourney.created_at.asc(), ContentJourney.id.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()


class MetricObservationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def add_many(self, rows: list[ContentMetricObservation]) -> None:
        self.db.add_all(rows)

    async def series(
        self, content_id: int, *, metric: str | None = None, since: datetime | None = None
    ) -> Sequence[ContentMetricObservation]:
        stmt = select(ContentMetricObservation).where(ContentMetricObservation.content_id == content_id)
        if metric:
            stmt = stmt.where(ContentMetricObservation.metric == metric)
        if since:
            stmt = stmt.where(ContentMetricObservation.observed_at >= since)
        stmt = stmt.order_by(ContentMetricObservation.observed_at.asc(), ContentMetricObservation.id.asc())
        return (await self.db.execute(stmt)).scalars().all()

    async def latest_by_metric(self, content_ids: list[int]) -> dict[int, dict[str, float]]:
        """每条内容每个指标的最新观测值。"""
        if not content_ids:
            return {}
        stmt = (
            select(ContentMetricObservation)
            .where(ContentMetricObservation.content_id.in_(content_ids))
            .order_by(ContentMetricObservation.observed_at.asc(), ContentMetricObservation.id.asc())
        )
        out: dict[int, dict[str, float]] = {}
        for row in (await self.db.execute(stmt)).scalars():
            out.setdefault(row.content_id, {})[row.metric] = row.value
        return out


class SourceRecentRepository:
    """采集页「最近采到」：某信源的最新内容 + 封面 + 观测序列。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def recent(self, source_id: int, *, limit: int):
        from app.models.content import ContentItem
        from app.models.content_observation import MediaAsset

        stmt = (
            select(ContentItem, MediaAsset.dominant_color, MediaAsset.status)
            .outerjoin(MediaAsset, MediaAsset.id == ContentItem.cover_asset_id)
            .where(ContentItem.source_id == source_id)
            .order_by(ContentItem.crawled_at.desc(), ContentItem.id.desc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).all()

    async def series_for(self, content_ids: list[int]) -> Sequence[ContentMetricObservation]:
        if not content_ids:
            return []
        stmt = (
            select(ContentMetricObservation)
            .where(ContentMetricObservation.content_id.in_(content_ids))
            .order_by(ContentMetricObservation.observed_at.asc(), ContentMetricObservation.id.asc())
        )
        return (await self.db.execute(stmt)).scalars().all()
