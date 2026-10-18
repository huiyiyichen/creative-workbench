"""初筛需要的聚合查询。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.content import ContentItem, ContentStatus
from app.models.favorite import FavoriteItem, FavoriteTargetType
from app.models.source import Source, SourceKind


class TriageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def setting(self, key: str) -> str | None:
        return await self.db.scalar(select(AppSetting.value).where(AppSetting.key == key))

    async def source_value_counts(self) -> tuple[dict[int, int], dict[int, int]]:
        """每个信源：被收藏的内容数、已分析的内容数（近 90 天全部，单用户量级可直接聚合）。"""
        fav_stmt = (
            select(ContentItem.source_id, func.count(FavoriteItem.id))
            .join(ContentItem, ContentItem.id == FavoriteItem.target_id)
            .where(FavoriteItem.target_type == FavoriteTargetType.CONTENT, ContentItem.source_id.is_not(None))
            .group_by(ContentItem.source_id)
        )
        analyzed_stmt = (
            select(ContentItem.source_id, func.count(ContentItem.id))
            .where(ContentItem.status == ContentStatus.ANALYZED, ContentItem.source_id.is_not(None))
            .group_by(ContentItem.source_id)
        )
        favorites = {int(k): int(v) for k, v in (await self.db.execute(fav_stmt)).all()}
        analyzed = {int(k): int(v) for k, v in (await self.db.execute(analyzed_stmt)).all()}
        return favorites, analyzed

    async def tracked_keywords(self) -> list[str]:
        stmt = select(Source.query, Source.name).where(
            Source.kind == SourceKind.KEYWORD.value, Source.enabled.is_(True)
        )
        out = []
        for query, name in (await self.db.execute(stmt)).all():
            word = (query or name or "").strip()
            if word:
                out.append(word)
        return out
