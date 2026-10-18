"""统一添加信源（改造方案 3.1）：识别 → 创建 → 首次同步由调用方决定。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source, SourceKind, SourceStatus, SourceType
from app.repositories.source_repo import SourceRepository
from app.services.platforms import ADAPTERS, SEARCH

# 默认间隔：追踪词 2 小时，榜单 1 小时，订阅 3 小时
DEFAULT_INTERVALS = {SourceKind.KEYWORD.value: 120, SourceKind.LIST.value: 60, SourceKind.SUBSCRIPTION.value: 180}


class SourceExistsError(Exception):
    pass


def searchable_platforms() -> list[str]:
    return [name for name, cls in ADAPTERS.items() if SEARCH in cls.capabilities]


async def create_source(db: AsyncSession, data: dict[str, Any]) -> Source:
    repo = SourceRepository(db)
    url = (data.get("url") or "").strip()
    if not url:
        raise ValueError("缺少信源地址")
    if url in await repo.find_existing_urls([url]):
        raise SourceExistsError("这个信源已经添加过了")
    kind = data.get("kind") or SourceKind.SUBSCRIPTION.value
    if kind not in SourceKind._value2member_map_:
        raise ValueError(f"未知信源类型 {kind}")
    source_type = SourceType(data.get("source_type") or SourceType.RSS.value)
    platforms = data.get("platforms")
    if kind == SourceKind.KEYWORD.value:
        allowed = set(searchable_platforms())
        platforms = [p for p in (platforms or []) if p in allowed] or None
    max_order = await repo.get_max_sort_order()
    source = Source(
        name=(data.get("name") or data.get("query") or url)[:255],
        source_type=source_type,
        url=url,
        platform=data.get("platform") or ("multi" if kind == SourceKind.KEYWORD.value else None),
        kind=kind,
        query=(data.get("query") or None),
        platforms=platforms,
        keyword=data.get("keyword"),
        enabled=True,
        status=SourceStatus.ACTIVE,
        fetch_interval_minutes=int(data.get("interval_minutes") or DEFAULT_INTERVALS[kind]),
        sort_order=(max_order or 0) + 1,
    )
    db.add(source)
    await db.flush()
    return source
