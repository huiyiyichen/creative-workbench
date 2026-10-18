"""Reddit 适配器：子版块（订阅）、全站搜索（追踪词）、评论，走公开 ``.json``。"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import COMMENTS, DETAIL, LIST_POSTS, SEARCH, Comment, PlatformAdapter, from_timestamp, https

BASE = "https://www.reddit.com"


class RedditAdapter(PlatformAdapter):
    platform = "reddit"
    label = "Reddit"
    capabilities: ClassVar[frozenset[str]] = frozenset({LIST_POSTS, SEARCH, DETAIL, COMMENTS})

    def to_entry(self, d: dict[str, Any]) -> dict[str, Any]:
        preview = ((d.get("preview") or {}).get("images") or [{}])[0].get("source", {}).get("url")
        thumb = d.get("thumbnail") if str(d.get("thumbnail") or "").startswith("http") else None
        cover = (preview or thumb or "").replace("&amp;", "&") or None
        permalink = f"{BASE}{d.get('permalink')}" if d.get("permalink") else None
        is_video = bool(d.get("is_video"))
        metrics = {"score": d.get("score"), "comments": d.get("num_comments")}
        return {
            "title": d.get("title") or "",
            "url": permalink or d.get("url") or "",
            "summary": (d.get("selftext") or "")[:1000] or None,
            "author": d.get("author"),
            "author_url": f"{BASE}/user/{d['author']}" if d.get("author") else None,
            "published_at": from_timestamp(d.get("created_utc")),
            "cover_url": https(cover),
            "platform": self.platform,
            "media_type": "video" if is_video else "post",
            "platform_item_id": d.get("id"),
            "media": {"subreddit": d.get("subreddit"), "link": d.get("url")},
            "metrics": {k: v for k, v in metrics.items() if isinstance(v, int)},
        }

    async def _get_json(self, url: str, **kwargs: Any) -> Any:
        # Reddit 要求描述性 UA；浏览器 UA 反而更容易被拒
        headers = {"User-Agent": "windows:creative-workbench:1.0 (local single-user app)", **kwargs.pop("headers", {})}
        return await super()._get_json(url, headers=headers, **kwargs)

    def _children(self, data: Any) -> list[dict[str, Any]]:
        return [
            c.get("data") or {} for c in ((data or {}).get("data") or {}).get("children") or [] if c.get("kind") == "t3"
        ]

    async def list_posts(self, target: str, *, limit: int = 20) -> list[dict[str, Any]]:
        sub = target.strip().removeprefix("r/").strip("/")
        data = await self._get_json(f"{BASE}/r/{sub}/new.json", params={"limit": min(limit, 50), "raw_json": 1})
        return [self.to_entry(d) for d in self._children(data)[:limit]]

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._get_json(
            f"{BASE}/search.json",
            params={"q": query, "sort": "new", "t": "week", "limit": min(limit, 50), "raw_json": 1},
        )
        return [self.to_entry(d) for d in self._children(data)[:limit]]

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        data = await self._get_json(f"{BASE}/comments/{item_id}.json", params={"limit": 1, "raw_json": 1})
        return self.to_entry(self._children(data[0])[0])

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        data = await self._get_json(
            f"{BASE}/comments/{item_id}.json", params={"sort": "top", "limit": limit, "depth": 1, "raw_json": 1}
        )
        rows = [
            c.get("data") or {}
            for c in ((data[1] or {}).get("data") or {}).get("children") or []
            if c.get("kind") == "t1"
        ]
        return [
            Comment(
                text=r.get("body") or "",
                author=r.get("author"),
                likes=r.get("score"),
                published_at=from_timestamp(r.get("created_utc")),
            )
            for r in rows[:limit]
        ]
