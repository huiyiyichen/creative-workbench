"""事件归并（改造方案 4.1）的数据访问：向量、窗口内候选、事件成员。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_event import ContentEventGroup, ContentEventMember
from app.models.content_observation import ContentEmbedding


class EventMergeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def contents_without_embedding(self, *, since: datetime, limit: int) -> Sequence[ContentItem]:
        has_vec = select(ContentEmbedding.content_id)
        stmt = (
            select(ContentItem)
            .where(
                ContentItem.crawled_at >= since,
                ContentItem.skip_analysis.is_(False),
                ContentItem.id.not_in(has_vec),
            )
            .order_by(ContentItem.crawled_at.asc(), ContentItem.id.asc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def window_vectors(self, *, since: datetime) -> list[tuple[int, bytes]]:
        stmt = (
            select(ContentEmbedding.content_id, ContentEmbedding.vector)
            .join(ContentItem, ContentItem.id == ContentEmbedding.content_id)
            .where(ContentItem.crawled_at >= since)
        )
        return [(int(cid), vec) for cid, vec in (await self.db.execute(stmt)).all()]

    async def favorite_vectors(self, *, limit: int = 500) -> list[bytes]:
        stmt = (
            select(ContentEmbedding.vector)
            .join(ContentItem, ContentItem.id == ContentEmbedding.content_id)
            .where(ContentItem.is_favorited.is_(True))
            .order_by(ContentItem.crawled_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def group_of(self, content_id: int) -> ContentEventGroup | None:
        group = await self.db.scalar(
            select(ContentEventGroup).where(ContentEventGroup.canonical_content_id == content_id)
        )
        if group is not None:
            return group
        stmt = (
            select(ContentEventGroup)
            .join(ContentEventMember, ContentEventMember.event_group_id == ContentEventGroup.id)
            .where(ContentEventMember.content_id == content_id)
        )
        return await self.db.scalar(stmt)

    async def group_content_ids(self, group: ContentEventGroup) -> list[int]:
        ids = (
            (
                await self.db.execute(
                    select(ContentEventMember.content_id).where(ContentEventMember.event_group_id == group.id)
                )
            )
            .scalars()
            .all()
        )
        return [group.canonical_content_id, *ids]

    async def contents(self, ids: list[int]) -> Sequence[ContentItem]:
        if not ids:
            return []
        return (await self.db.execute(select(ContentItem).where(ContentItem.id.in_(ids)))).scalars().all()
