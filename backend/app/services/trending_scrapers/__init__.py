"""
趋势雷达 scraper 注册表和基类。

比内容 scraper 更轻量：
- 不走 LLM
- 返回 TrendingEntry dict
- pipeline 只做批量替换存储
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── 类型别名 ──────────────────────────────────────────────────────
TrendingEntry = dict[str, Any]
# 必须包含: title, rank, hot_value
# 可选包含: url, hot_value_raw, trend, cover_url, extra

# trending_items.title 是 varchar(500)。各 scraper 抓取的外部 title 无长度
# 上限，在 PostgreSQL 上会触发 StringDataRightTruncation 整批回滚（SQLite
# 不强制 VARCHAR 长度故不会报错）。统一截断到 480 + 省略号。
TITLE_MAX = 480


def truncate_title(text: str) -> str:
    """截断 title 到 TITLE_MAX，超长加省略号（中英文都安全）。"""
    if len(text) <= TITLE_MAX:
        return text
    return text[: TITLE_MAX - 1] + "…"


# ── Registry ──────────────────────────────────────────────────────
_TRENDING_REGISTRY: dict[str, type] = {}


def register_trending(source: str):
    """Decorator: register a trending scraper."""

    def _cls(cls):
        _TRENDING_REGISTRY[source] = cls
        return cls

    return _cls


def get_trending_cls(source: str) -> type | None:
    return _TRENDING_REGISTRY.get(source)


def get_all_trending_sources() -> list[str]:
    return list(_TRENDING_REGISTRY.keys())


def get_syncable_trending_sources() -> list[str]:
    """定时全量同步用的公开热点信源列表。"""
    return list(_TRENDING_REGISTRY)


# Compatibility for snapshot code and historical tests. No active source is
# excluded from the public trending sync registry.
SYNC_EXCLUDED_SOURCES: frozenset[str] = frozenset()


# ── Base class ────────────────────────────────────────────────────
# 多数榜单站点会拒绝 default Python-httpx UA（返回 403/406），故各 scraper
# 统一伪装成桌面 Chrome。集中维护，避免 16+ 处硬编码漂移。
# 取自 settings.HTTP_BROWSER_USER_AGENT,部署时可在 .env 中统一覆盖。
BROWSER_UA = settings.HTTP_BROWSER_USER_AGENT


class BaseTrendingScraper(ABC):
    """榜单 scraper 基类。"""

    # 子类必须设置
    SOURCE: str = ""
    CATEGORY: str = ""  # TrendingCategory value

    def _build_headers(self, **extra: str) -> dict[str, str]:
        """构造请求头。默认带 BROWSER_UA，子类只补充 Referer/Accept/Cookie 等。

        示例::

            headers = self._build_headers(Referer="https://.../", Accept="application/json")
        """
        return {"User-Agent": BROWSER_UA, **extra}

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> Any | None:
        """GET 并解析 JSON。失败时记 warning 日志并返回 None（统一 fetch 样板）。

        子类拿到 None 即可 ``return []``，无需再写 try/except/raise_for_status。
        """
        try:
            resp = await client.get(url, headers=headers or {})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("%s trending fetch failed: %s", self.SOURCE or type(self).__name__, e)
            return None

    async def _fetch_text(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> str | None:
        """GET 并返回响应文本（HTML/XML）。失败时记 warning 日志并返回 None。"""
        try:
            resp = await client.get(url, headers=headers or {})
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning("%s trending fetch failed: %s", self.SOURCE or type(self).__name__, e)
            return None

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[TrendingEntry]:
        """
        抓取榜单，返回条目列表。
        每个条目:
          title: str       标题/关键词
          rank: int        排名
          url: str         链接
          hot_value: int   热度值（数字）
          hot_value_raw: str  原始热度文本
          trend: str       "up"/"down"/"new"/"stable"
          cover_url: str   封面图
          extra: dict      平台特有数据
        """
        ...


# ── Auto-import submodules ───────────────────────────────────────
from . import (  # noqa: E402, F401
    _baidu,
    _bilibili,
    _douban,
    _douyin_trending,
    _eastmoney,
    _github,
    _hackernews,
    _hupu,
    _ithome,
    _juejin,
    _kr36,
    _sspai,
    _toutiao,
    _v2ex,
    _weibo,
    # 中文播客榜（公开 API）
    _xyzrank,
    # 以下接口暂不可用，保留代码待修复
    # _tieba,
    # _netease,
    # _xueqiu,
    # _sohu,
    _zhihu_trending,
)
