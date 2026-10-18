"""平台适配器注册表（改造方案 3.2）。B站、YouTube、GitHub、HN、Reddit 先行。"""

from __future__ import annotations

import os

import httpx

from .base import (
    ALL_CAPABILITIES,
    COMMENTS,
    DETAIL,
    LIST_POSTS,
    RANKING,
    SEARCH,
    SUBTITLES,
    Comment,
    NotSupported,
    PlatformAdapter,
    PlatformError,
    SubtitleTrack,
)
from .bilibili import BilibiliAdapter
from .github import GithubAdapter
from .hn import HackerNewsAdapter
from .reddit import RedditAdapter
from .youtube import YoutubeAdapter

ADAPTERS: dict[str, type[PlatformAdapter]] = {
    cls.platform: cls for cls in (BilibiliAdapter, YoutubeAdapter, GithubAdapter, HackerNewsAdapter, RedditAdapter)
}
# 平台 API Key 的环境变量名；设置页保存的值优先（见 platform_keys）
KEY_ENV = {"youtube": "YOUTUBE_API_KEY", "github": "GITHUB_TOKEN"}


def get_adapter(platform: str, client: httpx.AsyncClient, *, api_key: str | None = None) -> PlatformAdapter:
    cls = ADAPTERS.get((platform or "").lower())
    if cls is None:
        raise NotSupported(f"平台 {platform} 暂未接入")
    key = api_key or (os.environ.get(KEY_ENV[platform]) if platform in KEY_ENV else None)
    return cls(client, api_key=key or None)


def describe_platforms() -> list[dict]:
    return [
        {
            "platform": name,
            "label": cls.label,
            "capabilities": {cap: cap in cls.capabilities for cap in ALL_CAPABILITIES},
            "needs_key": name in KEY_ENV,
        }
        for name, cls in ADAPTERS.items()
    ]


__all__ = [
    "ADAPTERS",
    "KEY_ENV",
    "COMMENTS",
    "DETAIL",
    "LIST_POSTS",
    "RANKING",
    "SEARCH",
    "SUBTITLES",
    "Comment",
    "NotSupported",
    "PlatformAdapter",
    "PlatformError",
    "SubtitleTrack",
    "describe_platforms",
    "get_adapter",
]
