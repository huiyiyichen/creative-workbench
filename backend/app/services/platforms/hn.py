"""Hacker News 适配器：Algolia 搜索（追踪词）、首页榜单、评论。"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import COMMENTS, DETAIL, RANKING, SEARCH, Comment, PlatformAdapter, from_timestamp, strip_tags

ALGOLIA = "https://hn.algolia.com/api/v1"


class HackerNewsAdapter(PlatformAdapter):
    platform = "hn"
    label = "Hacker News"
    capabilities: ClassVar[frozenset[str]] = frozenset({SEARCH, RANKING, DETAIL, COMMENTS})

    def to_entry(self, hit: dict[str, Any]) -> dict[str, Any]:
        oid = str(hit.get("objectID") or hit.get("id") or "")
        discuss = f"https://news.ycombinator.com/item?id={oid}"
        metrics = {"score": hit.get("points"), "comments": hit.get("num_comments")}
        return {
            "title": hit.get("title") or hit.get("story_title") or "",
            "url": hit.get("url") or discuss,
            "summary": strip_tags(hit.get("story_text") or hit.get("text")) or None,
            "author": hit.get("author"),
            "author_url": f"https://news.ycombinator.com/user?id={hit['author']}" if hit.get("author") else None,
            "published_at": from_timestamp(hit.get("created_at_i")),
            "platform": self.platform,
            "media_type": "post",
            "platform_item_id": oid or None,
            "media": {"discussion_url": discuss},
            "metrics": {k: v for k, v in metrics.items() if isinstance(v, int)},
        }

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._get_json(
            f"{ALGOLIA}/search_by_date", params={"query": query, "tags": "story", "hitsPerPage": min(limit, 50)}
        )
        return [self.to_entry(h) for h in (data.get("hits") or [])[:limit]]

    async def list_ranking(self, name: str = "", *, limit: int = 30) -> list[dict[str, Any]]:
        data = await self._get_json(f"{ALGOLIA}/search", params={"tags": "front_page", "hitsPerPage": min(limit, 50)})
        entries = []
        for rank, hit in enumerate((data.get("hits") or [])[:limit], start=1):
            entry = self.to_entry(hit)
            entry["metrics"]["rank"] = rank
            entries.append(entry)
        return entries

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        item = await self._get_json(f"{ALGOLIA}/items/{item_id}")
        item["objectID"] = item.get("id")
        item["created_at_i"] = item.get("created_at_i")
        return self.to_entry(item)

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        item = await self._get_json(f"{ALGOLIA}/items/{item_id}")
        children = [c for c in item.get("children") or [] if c.get("text")]
        # 按回复数近似热度
        children.sort(key=lambda c: len(c.get("children") or []), reverse=True)
        return [
            Comment(
                text=strip_tags(c.get("text")),
                author=c.get("author"),
                replies=len(c.get("children") or []),
                published_at=from_timestamp(c.get("created_at_i")),
            )
            for c in children[:limit]
        ]
