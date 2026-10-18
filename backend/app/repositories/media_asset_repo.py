"""封面缓存（改造方案 3.4）的数据访问。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_observation import MediaAsset, MediaAssetStatus


class MediaAssetRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, asset_id: int) -> MediaAsset | None:
        return await self.db.get(MediaAsset, asset_id)

    async def by_hash(self, url_hash: str) -> MediaAsset | None:
        return await self.db.scalar(select(MediaAsset).where(MediaAsset.url_hash == url_hash))

    async def contents_without_asset(self, *, limit: int, since: datetime) -> Sequence[ContentItem]:
        stmt = (
            select(ContentItem)
            .where(
                ContentItem.cover_url.is_not(None),
                ContentItem.cover_url != "",
                ContentItem.cover_asset_id.is_(None),
                ContentItem.crawled_at >= since,
            )
            .order_by(ContentItem.crawled_at.desc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def total_bytes(self) -> int:
        return int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(MediaAsset.bytes), 0)).where(
                        MediaAsset.status == MediaAssetStatus.READY.value
                    )
                )
            ).scalar()
            or 0
        )

    async def eviction_candidates(self, *, limit: int = 200) -> Sequence[MediaAsset]:
        """最久未访问的、未固定、且没有被收藏内容引用的封面。"""
        favorited = select(ContentItem.cover_asset_id).where(
            ContentItem.is_favorited.is_(True), ContentItem.cover_asset_id.is_not(None)
        )
        stmt = (
            select(MediaAsset)
            .where(
                MediaAsset.status == MediaAssetStatus.READY.value,
                MediaAsset.pinned.is_(False),
                MediaAsset.id.not_in(favorited),
            )
            .order_by(func.coalesce(MediaAsset.last_accessed_at, MediaAsset.created_at).asc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def touch(self, asset_id: int, at: datetime) -> None:
        await self.db.execute(update(MediaAsset).where(MediaAsset.id == asset_id).values(last_accessed_at=at))

    async def detach(self, asset_id: int) -> None:
        await self.db.execute(
            update(ContentItem).where(ContentItem.cover_asset_id == asset_id).values(cover_asset_id=None)
        )
