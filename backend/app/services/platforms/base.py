"""平台适配器统一接口（改造方案 3.2）。

每个平台实现 ``list_posts``（订阅：账号 / 频道 / 仓库）、``search``（追踪词）、
``list_ranking``（榜单）、``fetch_detail``、``fetch_comments``、``fetch_subtitles``；
不支持的能力在 ``capabilities`` 里不出现，调用时抛 :class:`NotSupported`。

返回的条目是采集管线的标准 entry（见 ``content_enrichment``）：
``title``、``url``、``summary``、``author``、``published_at``、``cover_url``、``platform``、
``media_type``、``platform_item_id``、``author_id``、``author_url``、``media``、``metrics``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

LIST_POSTS = "list_posts"
SEARCH = "search"
RANKING = "list_ranking"
DETAIL = "fetch_detail"
COMMENTS = "fetch_comments"
SUBTITLES = "fetch_subtitles"
ALL_CAPABILITIES = (LIST_POSTS, SEARCH, RANKING, DETAIL, COMMENTS, SUBTITLES)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " "Chrome/126.0 Safari/537.36"
)


class NotSupported(Exception):  # noqa: N818 — 与「不支持」语义一致
    """该平台不支持这个能力（或缺少必需的 API Key）。"""


class PlatformError(Exception):
    """平台返回错误（限流、风控、接口变更）。message 写给用户看。"""


@dataclass
class Comment:
    text: str
    author: str | None = None
    likes: int | None = None
    published_at: datetime | None = None
    replies: int | None = None
    id: str | None = None  # 平台内评论 id，重复采集时据此更新


@dataclass
class SubtitleTrack:
    language: str
    text: str
    segments: list[dict[str, Any]] = field(default_factory=list)


class PlatformAdapter:
    platform: ClassVar[str] = ""
    label: ClassVar[str] = ""
    capabilities: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, client: httpx.AsyncClient, *, api_key: str | None = None):
        self.client = client
        self.api_key = api_key

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    # 订阅能否按页往回翻（空档补采用）
    supports_paging: ClassVar[bool] = False

    async def list_posts(self, target: str, *, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        raise NotSupported(f"{self.label} 不支持订阅")

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        raise NotSupported(f"{self.label} 不支持搜索")

    async def list_ranking(self, name: str = "", *, limit: int = 30) -> list[dict[str, Any]]:
        raise NotSupported(f"{self.label} 没有榜单")

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        raise NotSupported(f"{self.label} 不支持读取详情")

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        raise NotSupported(f"{self.label} 没有评论来源")

    async def fetch_subtitles(self, item_id: str) -> list[SubtitleTrack]:
        raise NotSupported(f"{self.label} 不支持字幕")

    async def _get_json(self, url: str, **kwargs: Any) -> Any:
        # 采集管线的共享客户端默认 Accept 是 RSS；平台接口要按浏览器请求 JSON，否则容易触发风控
        headers = {
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            **kwargs.pop("headers", {}),
        }
        resp = await self.client.get(url, headers=headers, **kwargs)
        if resp.status_code == 429:
            raise PlatformError(f"{self.label} 限流（429）")
        if resp.status_code in (401, 403):
            raise PlatformError(f"{self.label} 拒绝访问（{resp.status_code}），可能需要 API Key 或登录")
        resp.raise_for_status()
        return resp.json()


_TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: str | None) -> str:
    import html

    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def from_timestamp(value: Any) -> datetime | None:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=UTC)


def from_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_duration(value: Any) -> int | None:
    """'12:34' / '1:02:03' / 754 / 'PT1H2M3S' → 秒。"""
    if value is None:
        return None
    if isinstance(value, int | float):
        return int(value)
    text = str(value).strip()
    iso = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
    if iso and any(iso.groups()):
        h, m, s = (int(g or 0) for g in iso.groups())
        return h * 3600 + m * 60 + s
    parts = text.split(":")
    if all(p.isdigit() for p in parts) and 1 <= len(parts) <= 3:
        total = 0
        for p in parts:
            total = total * 60 + int(p)
        return total
    return None


def https(url: str | None) -> str | None:
    if not url:
        return None
    return "https:" + url if url.startswith("//") else url.replace("http://", "https://", 1)
