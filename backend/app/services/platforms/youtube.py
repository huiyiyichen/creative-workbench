"""YouTube 适配器：频道 RSS（订阅，无需 Key）；搜索 / 详情 / 评论走 Data API（需要 API Key）。"""

from __future__ import annotations

import re
from typing import Any, ClassVar

import feedparser

from .base import COMMENTS, DETAIL, LIST_POSTS, SEARCH, Comment, NotSupported, PlatformAdapter, from_iso, parse_duration

DATA_API = "https://www.googleapis.com/youtube/v3"
FEED = "https://www.youtube.com/feeds/videos.xml"
_CHANNEL_RE = re.compile(r"(UC[\w-]{22})")


def thumbnail(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


class YoutubeAdapter(PlatformAdapter):
    platform = "youtube"
    label = "YouTube"
    capabilities: ClassVar[frozenset[str]] = frozenset({LIST_POSTS, SEARCH, DETAIL, COMMENTS})

    def _need_key(self) -> str:
        if not self.api_key:
            raise NotSupported("YouTube 搜索需要在设置里填写 Data API Key")
        return self.api_key

    async def list_posts(self, target: str, *, limit: int = 20) -> list[dict[str, Any]]:
        match = _CHANNEL_RE.search(target)
        if not match:
            raise NotSupported("YouTube 订阅需要频道 ID（UC 开头）")
        resp = await self.client.get(FEED, params={"channel_id": match.group(1)})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        out = []
        for e in feed.entries[:limit]:
            vid = e.get("yt_videoid") or ""
            stats = e.get("media_statistics") or {}
            views = stats.get("views")
            out.append(
                {
                    "title": e.get("title") or "",
                    "url": e.get("link") or f"https://www.youtube.com/watch?v={vid}",
                    "summary": (e.get("media_description") or e.get("summary") or "")[:1000] or None,
                    "author": e.get("author"),
                    "author_id": match.group(1),
                    "author_url": f"https://www.youtube.com/channel/{match.group(1)}",
                    "published_at": from_iso(e.get("published")),
                    "cover_url": thumbnail(vid) if vid else None,
                    "platform": self.platform,
                    "media_type": "video",
                    "platform_item_id": vid or None,
                    "media": {"orientation": "portrait" if "/shorts/" in (e.get("link") or "") else None},
                    "metrics": {"views": int(views)} if str(views or "").isdigit() else {},
                }
            )
        return out

    def _video_entry(self, v: dict[str, Any]) -> dict[str, Any]:
        sn = v.get("snippet") or {}
        st = v.get("statistics") or {}
        vid = v["id"]["videoId"] if isinstance(v.get("id"), dict) else v.get("id")
        metrics = {
            k: int(st[s])
            for k, s in (("views", "viewCount"), ("likes", "likeCount"), ("comments", "commentCount"))
            if str(st.get(s, "")).isdigit()
        }
        duration = parse_duration((v.get("contentDetails") or {}).get("duration"))
        return {
            "title": sn.get("title") or "",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "summary": (sn.get("description") or "")[:1000] or None,
            "author": sn.get("channelTitle"),
            "author_id": sn.get("channelId"),
            "author_url": f"https://www.youtube.com/channel/{sn['channelId']}" if sn.get("channelId") else None,
            "published_at": from_iso(sn.get("publishedAt")),
            "cover_url": thumbnail(vid),
            "platform": self.platform,
            "media_type": "video",
            "platform_item_id": vid,
            "media": {"duration": duration} if duration else {},
            "metrics": metrics,
            "tags": (sn.get("tags") or [])[:5],
        }

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        key = self._need_key()
        data = await self._get_json(
            f"{DATA_API}/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "date",
                "maxResults": min(limit, 50),
                "key": key,
            },
        )
        ids = [i["id"]["videoId"] for i in data.get("items") or [] if (i.get("id") or {}).get("videoId")]
        if not ids:
            return []
        videos = await self._get_json(
            f"{DATA_API}/videos", params={"part": "snippet,statistics,contentDetails", "id": ",".join(ids), "key": key}
        )
        return [self._video_entry(v) for v in videos.get("items") or []]

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        data = await self._get_json(
            f"{DATA_API}/videos",
            params={"part": "snippet,statistics,contentDetails", "id": item_id, "key": self._need_key()},
        )
        items = data.get("items") or []
        if not items:
            raise NotSupported("视频不存在或不可见")
        return self._video_entry(items[0])

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        data = await self._get_json(
            f"{DATA_API}/commentThreads",
            params={
                "part": "snippet",
                "videoId": item_id,
                "order": "relevance",
                "maxResults": min(limit, 100),
                "key": self._need_key(),
            },
        )
        out = []
        for t in data.get("items") or []:
            top = ((t.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {}
            out.append(
                Comment(
                    text=top.get("textOriginal") or "",
                    author=top.get("authorDisplayName"),
                    likes=top.get("likeCount"),
                    replies=(t.get("snippet") or {}).get("totalReplyCount"),
                    published_at=from_iso(top.get("publishedAt")),
                )
            )
        return out
