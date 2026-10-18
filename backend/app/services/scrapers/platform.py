"""平台适配器信源（改造方案 3.1 / 3.2）。

* ``Platform``：订阅或榜单。url 形如 ``platform://bilibili/user/946974``、
  ``platform://github/repo/owner/name``、``platform://bilibili/ranking/popular``、
  ``platform://github/ranking/daily``。
* ``Keyword``：追踪词。``query`` 在多个平台同时搜索（``platforms`` 为空时搜全部支持搜索的平台）。
  每个平台单独计错：一个平台失败不影响其他平台；全部失败才算本次同步失败。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote

import httpx

from app.services.platforms import ADAPTERS, SEARCH, NotSupported, get_adapter

from . import BaseScraper, register_scraper

logger = logging.getLogger(__name__)

DEFAULT_KEYWORD_PLATFORMS = ("bilibili", "youtube", "github", "hn", "reddit")
PER_PLATFORM_LIMIT = 10


def parse_platform_url(url: str) -> tuple[str, str, str]:
    """``platform://bilibili/user/946974`` → (bilibili, user, 946974)。"""
    rest = url.split("://", 1)[1] if "://" in url else url
    parts = rest.split("/", 2)
    if len(parts) < 2:
        raise ValueError(f"无法识别的平台信源地址：{url}")
    platform, mode = parts[0], parts[1]
    target = unquote(parts[2]) if len(parts) > 2 else ""
    return platform.lower(), mode, target


@register_scraper("Platform")
class PlatformScraper(BaseScraper):
    async def fetch(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        platform, mode, target = parse_platform_url(self.url)
        adapter = get_adapter(platform, client, api_key=(self.config.get("api_keys") or {}).get(platform))
        if mode == "ranking":
            return await adapter.list_ranking(target)
        return await adapter.list_posts(target)


@register_scraper("Keyword")
class KeywordScraper(BaseScraper):
    """一个词多个平台搜索；结果按平台合并，每个平台最多 10 条。"""

    def __init__(self, source_url: str, source_config: dict[str, Any] | None = None):
        super().__init__(source_url, source_config)
        self.platform_errors: dict[str, str] = {}

    def _query(self) -> str:
        query = (self.config.get("query") or "").strip()
        if not query and "://" in self.url:
            query = unquote(self.url.split("://", 1)[1]).strip()
        return query

    async def fetch(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        query = self._query()
        if not query:
            raise ValueError("追踪词为空")
        platforms = self.config.get("platforms") or list(DEFAULT_KEYWORD_PLATFORMS)
        entries: list[dict[str, Any]] = []
        attempted = 0
        failed = 0
        for platform in platforms:
            if platform not in ADAPTERS or SEARCH not in ADAPTERS[platform].capabilities:
                continue
            adapter = get_adapter(platform, client, api_key=(self.config.get("api_keys") or {}).get(platform))
            try:
                found = await adapter.search(query, limit=PER_PLATFORM_LIMIT)
            except NotSupported as exc:  # 缺 Key 等：只记录，不算失败
                self.platform_errors[platform] = str(exc)
                continue
            except Exception as exc:  # 单个平台失败不影响其他平台
                logger.warning("keyword %r on %s failed: %s", query, platform, exc)
                self.platform_errors[platform] = str(exc)[:200]
                attempted += 1
                failed += 1
                continue
            attempted += 1
            for entry in found:
                entry.setdefault("platform", platform)
                entry.setdefault("_keyword", query)
            entries.extend(found)
        if attempted and failed == attempted:
            raise RuntimeError("；".join(f"{p}：{e}" for p, e in self.platform_errors.items()))
        return entries
