"""抖音（改造方案 3.2）：本机浏览器打开主页 / 搜索页 / 视频页，读页面自身的接口响应。

* 订阅：``platform://douyin/user/<sec_uid>`` → ``/aweme/v1/web/aweme/post/``
* 搜索：``https://www.douyin.com/search/<词>?type=video`` → ``/aweme/v1/web/search/item/``（或 general 搜索）
* 详情：``https://www.douyin.com/video/<aweme_id>`` → ``/aweme/v1/web/aweme/detail/``
* 评论：同一视频页 → ``/aweme/v1/web/comment/list/``，按页面默认的热度顺序取前 N 条，不取回复。
"""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import quote

from . import browser
from .base import COMMENTS, DETAIL, LIST_POSTS, SEARCH, Comment, PlatformAdapter, PlatformError, from_timestamp, https


def _cover(video: dict[str, Any]) -> str | None:
    for key in ("cover", "origin_cover", "dynamic_cover"):
        urls = (video.get(key) or {}).get("url_list") or []
        if urls:
            return https(urls[-1])
    return None


def to_entry(post: dict[str, Any]) -> dict[str, Any] | None:
    aweme_id = str(post.get("aweme_id") or "")
    if not aweme_id:
        return None
    desc = (post.get("desc") or "").strip()
    author = post.get("author") or {}
    video = post.get("video") or {}
    stat = post.get("statistics") or {}
    images = post.get("images") or []
    w, h = video.get("width"), video.get("height")
    metrics = {
        "views": stat.get("play_count") or None,
        "likes": stat.get("digg_count"),
        "comments": stat.get("comment_count"),
        "favorites": stat.get("collect_count"),
        "shares": stat.get("share_count"),
    }
    duration_ms = video.get("duration") or post.get("duration")
    sec_uid = author.get("sec_uid")
    return {
        "title": (desc.split("\n")[0] or f"抖音作品 {aweme_id}")[:300],
        "url": f"https://www.douyin.com/video/{aweme_id}",
        "summary": desc or None,
        "author": author.get("nickname"),
        "author_id": sec_uid,
        "author_url": f"https://www.douyin.com/user/{sec_uid}" if sec_uid else None,
        "published_at": from_timestamp(post.get("create_time")),
        "cover_url": _cover(video) or (https(((images[0] or {}).get("url_list") or [None])[-1]) if images else None),
        "platform": "douyin",
        "media_type": "image" if images else "video",
        "platform_item_id": aweme_id,
        "media": {
            k: v
            for k, v in {
                "duration": int(duration_ms / 1000) if isinstance(duration_ms, int | float) and duration_ms else None,
                "orientation": ("portrait" if h > w else "landscape") if w and h else "portrait",
                "images": len(images) or None,
            }.items()
            if v
        },
        "metrics": {k: v for k, v in metrics.items() if isinstance(v, int | float) and v >= 0},
        "tags": [t["hashtag_name"] for t in post.get("text_extra") or [] if t.get("hashtag_name")][:8],
    }


def posts_from(payload: Any) -> list[dict[str, Any]]:
    """作品列表 / 搜索结果 / 综合搜索里的视频卡片 → 条目。"""
    if not isinstance(payload, dict):
        return []
    raw: list[dict[str, Any]] = []
    raw.extend(payload.get("aweme_list") or [])
    for d in payload.get("data") or []:
        if isinstance(d, dict):
            if d.get("aweme_info"):
                raw.append(d["aweme_info"])
            for m in d.get("aweme_mix_info", {}).get("mix_items") or []:
                raw.append(m)
    if payload.get("aweme_detail"):
        raw.append(payload["aweme_detail"])
    out, seen = [], set()
    for p in raw:
        e = to_entry(p)
        if e and e["platform_item_id"] not in seen:
            seen.add(e["platform_item_id"])
            out.append(e)
    return out


def comments_from(payload: Any, limit: int) -> list[Comment]:
    out = []
    for c in (payload or {}).get("comments") or []:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        out.append(
            Comment(
                text=text,
                author=(c.get("user") or {}).get("nickname"),
                likes=c.get("digg_count"),
                replies=c.get("reply_comment_total"),
                published_at=from_timestamp(c.get("create_time")),
                id=str(c["cid"]) if c.get("cid") else None,
            )
        )
    out.sort(key=lambda c: -(c.likes or 0))
    return out[:limit]


class DouyinAdapter(PlatformAdapter):
    platform: ClassVar[str] = "douyin"
    label: ClassVar[str] = "抖音"
    capabilities: ClassVar[frozenset[str]] = frozenset({LIST_POSTS, SEARCH, DETAIL, COMMENTS})
    browser_based: ClassVar[bool] = True

    async def list_posts(self, target: str, *, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        mode, _, uid = target.partition("/") if "/" in target else ("user", "", target)
        if mode != "user" or not uid.startswith("MS4w"):
            raise PlatformError("抖音订阅地址应为 platform://douyin/user/<sec_uid>（主页链接里 user/ 后面那段）")
        cap = await browser.BROWSER.capture(
            "douyin", f"https://www.douyin.com/user/{uid}", {"posts": "/aweme/v1/web/aweme/post/"}, scroll=1
        )
        items: list[dict[str, Any]] = []
        for payload in cap.responses.get("posts") or []:
            items.extend(posts_from(payload))
        return items[:limit]

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        cap = await browser.BROWSER.capture(
            "douyin",
            f"https://www.douyin.com/search/{quote(query)}?type=video",
            {"items": "/aweme/v1/web/search/item/", "general": "/aweme/v1/web/general/search/single/"},
            need=(),
            wait_seconds=20,
        )
        items: list[dict[str, Any]] = []
        for name in ("items", "general"):
            for payload in cap.responses.get(name) or []:
                items.extend(posts_from(payload))
        dedup = {e["platform_item_id"]: e for e in items}
        return list(dedup.values())[:limit]

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        cap = await browser.BROWSER.capture(
            "douyin", f"https://www.douyin.com/video/{item_id}", {"detail": "/aweme/v1/web/aweme/detail/"}
        )
        found = posts_from(cap.first("detail"))
        if not found:
            raise PlatformError("抖音详情接口没有返回作品（接口可能变化）")
        return found[0]

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        cap = await browser.BROWSER.capture(
            "douyin",
            f"https://www.douyin.com/video/{item_id}",
            {"comments": "/aweme/v1/web/comment/list/"},
            scroll=2,
        )
        out: list[Comment] = []
        for payload in cap.responses.get("comments") or []:
            out.extend(comments_from(payload, limit))
        dedup = {c.id or c.text: c for c in out}
        return sorted(dedup.values(), key=lambda c: -(c.likes or 0))[:limit]
