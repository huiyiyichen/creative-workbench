"""
URL → SourceType recognizer.

Pure-function, table-driven URL pattern matching. Used by import_opml /
batch import to pick the right scraper without asking the user to specify
source_type manually. Migrated from the hard-coded `xgo.ing` branch in
``app/api/v1/sources.py`` (T1-3b) and extended to YouTube / Podcast /
Newsletter / RSS feeds.

Returned tuple: ``(source_type, normalized_url, extra_keyword_config)``.
The third element (dict or None) is JSON-serialised into ``Source.keyword``
and read back by the matching scraper's ``__init__``.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, quote, urlparse

from app.models.source import SourceType


def recognize_source_type(
    url: str,
    *,
    name: str | None = None,
) -> tuple[SourceType, str, dict | None]:
    """Infer ``SourceType`` from a feed/page URL.

    Args:
        url: the source URL the user pasted (RSS feed, channel page, etc).
        name: optional display name. Used to extract ``@handle`` for xgo.ing
            Twitter RSS feeds where the handle is in the name rather than URL.

    Returns:
        ``(source_type, normalized_url, extra_config)``.

        - ``source_type`` is always set (defaults to :class:`SourceType.RSS`).
        - ``normalized_url`` is the URL to store (currently always the input;
          future revisions may rewrite e.g. bare handles).
        - ``extra_config`` is a dict serialised into ``Source.keyword`` when
          the scraper needs additional metadata (e.g. ``screen_name`` for
          Twitter RSS, ``channel_id`` for YouTube). ``None`` otherwise.
    """
    if not url:
        return SourceType.RSS, url, None

    # 已存储的 RSSHub 路由（无协议、无域名）：抖音账号曾被误识别成 DouyinHot 榜单类型
    # （问题清单 C3），这里让路由本身也能被识别回账号订阅。
    route_match = re.fullmatch(r"douyin/user/(MS4w[\w-]+)/?", url.strip())
    if route_match:
        return SourceType.RSSHub, f"douyin/user/{route_match.group(1)}", {
            "platform": "douyin", "original_url": f"https://www.douyin.com/user/{route_match.group(1)}",
        }

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""

    if host in {"douyin.com", "www.douyin.com"}:
        match = re.fullmatch(r"/user/(MS4w[\w-]+)/?", path)
        if match:
            return SourceType.RSSHub, f"douyin/user/{match.group(1)}", {
                "platform": "douyin", "original_url": f"https://www.douyin.com/user/{match.group(1)}",
            }
    # Bilibili creator pages are normalized to the RSSHub route consumed by
    # the existing RSSHub scraper. This keeps a pasted space.bilibili.com URL
    # as a first-class private signal source while preserving the creator id.
    if host in {"space.bilibili.com", "www.bilibili.com", "bilibili.com"}:
        match = re.search(r"(?:space\.bilibili\.com/|/space/)(\d+)", url)
        if match:
            return SourceType.RSSHub, f"bilibili/user/video-all/{match.group(1)}", {
                "platform": "bilibili", "query": f"UP主 {match.group(1)}",
                "original_url": f"https://space.bilibili.com/{match.group(1)}",
            }
    if host == "search.bilibili.com":
        keyword = parse_qs(parsed.query).get("keyword", [""])[0].strip()
        if keyword:
            return SourceType.RSSHub, f"bilibili/vsearch/{quote(keyword, safe='')}", {"platform": "bilibili", "query": keyword}
    if host in {"www.bilibili.com", "bilibili.com"} and (
        path.rstrip("/") in {"/hot", "/ranking"} or path.startswith("/v/popular/rank/")
    ):
        return SourceType.RSSHub, "bilibili/ranking/all", {"platform": "bilibili", "query": "热门视频"}
    if host in {"douyin.com", "www.douyin.com", "so.douyin.com"} and (
        path.rstrip("/") in {"/hot", "/hotlist"} or "hot" in path.lower()
    ):
        return SourceType.DOUYIN_HOT, "https://www.douyin.com/hot", {"platform": "douyin", "query": "抖音热榜"}

    # ── Twitter RSS via xgo.ing bridge ─────────────────────────────────
    if "xgo.ing" in host:
        screen_name = ""
        if name:
            # name like "OpenAI(@OpenAI)" or "OpenAI (@openai)"
            handle_match = re.search(r"\(@?(\w+)\)", name)
            if handle_match:
                screen_name = handle_match.group(1)
        if not screen_name:
            # fall back to path segment: xgo.ing/<user>/rss
            seg_match = re.search(r"xgo\.ing/([^/?#\s]+)", url, re.IGNORECASE)
            if seg_match and seg_match.group(1).lower() not in {"rss", "api"}:
                screen_name = seg_match.group(1)
        config = {"screen_name": screen_name} if screen_name else None
        return SourceType.TWITTER_RSS, url, config

    # ── YouTube ────────────────────────────────────────────────────────
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        # Already an RSS feed URL?
        m = re.search(r"channel_id=([A-Za-z0-9_-]+)", url)
        if m:
            return SourceType.YOUTUBE, url, {"channel_id": m.group(1)}
        # /channel/UCxxxx
        m = re.match(r"^/channel/([A-Za-z0-9_-]+)", path)
        if m:
            return SourceType.YOUTUBE, url, {"channel_id": m.group(1)}
        # /@handle or /user/name — scraper resolves channel_id at fetch time
        if re.match(r"^/@[\w.\-]+", path) or re.match(r"^/user/[^/]+", path):
            return SourceType.YOUTUBE, url, None
        # youtu.be/<video> — single video, treat as YouTube anyway
        if host == "youtu.be" and path.strip("/"):
            return SourceType.YOUTUBE, url, None
        return SourceType.YOUTUBE, url, None

    # ── Podcast ────────────────────────────────────────────────────────
    if host == "podcasts.apple.com" or host == "itunes.apple.com":
        # /us/podcast/<slug>/id<id>
        m = re.search(r"/id(\d+)", path)
        config = {"itunes_id": m.group(1)} if m else None
        return SourceType.PODCAST, url, config
    if host == "xiaoyuzhoufm.com" or host.endswith(".xiaoyuzhoufm.com"):
        return SourceType.PODCAST, url, None
    if host.endswith(".buzzsprout.com"):
        return SourceType.PODCAST, url, None
    if host.endswith(".podbean.com"):
        return SourceType.PODCAST, url, None
    if host in {"anchor.fm", "www.anchor.fm"} or host.endswith(".anchor.fm"):
        return SourceType.PODCAST, url, None
    if host in {"open.spotify.com"} and path.startswith("/show/"):
        return SourceType.PODCAST, url, None

    # ── Newsletter ─────────────────────────────────────────────────────
    if host == "buttondown.email":
        # buttondown.email/<name>
        m = re.match(r"^/([^/?#\s]+)", path)
        if m and m.group(1).lower() not in {"login", "signup", "about"}:
            return SourceType.NEWSLETTER, url, None
        return SourceType.NEWSLETTER, url, None
    if host.endswith(".substack.com"):
        return SourceType.NEWSLETTER, url, None
    if host.endswith(".beehiiv.com"):
        return SourceType.NEWSLETTER, url, None
    if host == "tinyletter.com" or host.endswith(".tinyletter.com"):
        return SourceType.NEWSLETTER, url, None
    if host == "convertkit.com" or host.endswith(".convertkit.com"):
        return SourceType.NEWSLETTER, url, None

    # ── RSS fallback (default + explicit feed hints) ───────────────────
    # Explicit RSS feed hints — keep as RSS but more confident.
    if host.startswith("feeds.") or path.endswith((".xml", ".rss", ".atom")) or "/feed" in path or "/rss" in path:
        return SourceType.RSS, url, None

    return SourceType.RSS, url, None


def normalize_creator_source(payload: dict, current=None) -> dict:
    url = payload.get("url", current.url if current is not None else "")
    source_type, normalized_url, config = recognize_source_type(url)
    if not config or config.get("platform") not in {"douyin", "bilibili"}:
        return payload
    keyword = payload.get("keyword", current.keyword if current is not None else None)
    try:
        existing = json.loads(keyword) if keyword else {}
    except (ValueError, TypeError):
        existing = {}
    payload.update(
        source_type=source_type, url=normalized_url,
        platform=config["platform"], keyword=json.dumps(
            {**(existing if isinstance(existing, dict) else {}), **config}, ensure_ascii=False,
        ),
    )
    return payload


# ── 统一添加（改造方案 3.1）：粘贴链接或输入关键词，自动识别信源类型 ─────────────

_GITHUB_RESERVED = {"trending", "topics", "explore", "search", "orgs", "settings", "marketplace", "sponsors"}


def recognize_input(text: str) -> dict:
    """返回 ``{kind, source_type, url, platform, query, name}``；识别结果可在界面上改。

    B站 / GitHub / YouTube 频道 / Reddit / HN 走平台适配器；其他链接沿用旧识别；
    不是链接的文字当作追踪词，在所有支持搜索的平台上搜索。
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("请输入链接或关键词")
    if not re.match(r"^(https?://|www\.|[\w.-]+\.(com|net|org|io|tv|me|fm|cn)(/|$))", raw, re.I):
        return {
            "kind": "keyword",
            "source_type": SourceType.KEYWORD.value,
            "url": f"keyword://{quote(raw, safe='')}",
            "platform": None,
            "query": raw,
            "name": raw,
        }
    url = raw if raw.startswith("http") else f"https://{raw}"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = parsed.path.rstrip("/")

    def platform(kind: str, name: str, plat: str, mode: str, target: str, query: str | None = None) -> dict:
        return {
            "kind": kind,
            "source_type": SourceType.PLATFORM.value,
            "url": f"platform://{plat}/{mode}/{target}",
            "platform": plat,
            "query": query,
            "name": name,
        }

    if host in {"space.bilibili.com", "bilibili.com"}:
        m = re.search(r"(?:space\.bilibili\.com/|/space/)(\d+)", url)
        if m:
            return platform("subscription", f"B站 UP 主 {m.group(1)}", "bilibili", "user", m.group(1))
        if path in {"/hot", "/ranking", "/v/popular/all"} or path.startswith("/v/popular"):
            return platform("list", "B站热门", "bilibili", "ranking", "popular")
        m = re.match(r"^/v/popular/rank/(\w+)", path)
        if m:
            return platform("list", f"B站排行 {m.group(1)}", "bilibili", "ranking", "popular")
    if host == "search.bilibili.com":
        keyword = parse_qs(parsed.query).get("keyword", [""])[0].strip()
        if keyword:
            return {
                "kind": "keyword",
                "source_type": SourceType.KEYWORD.value,
                "url": f"keyword://{quote(keyword, safe='')}",
                "platform": "bilibili",
                "platforms": ["bilibili"],
                "query": keyword,
                "name": keyword,
            }
    if host == "github.com":
        parts = [p for p in path.split("/") if p]
        if parts and parts[0] == "trending":
            since = parse_qs(parsed.query).get("since", ["daily"])[0]
            target = f"{parts[1]}:{since}" if len(parts) > 1 else since
            return platform("list", "GitHub Trending", "github", "ranking", target)
        if len(parts) >= 2 and parts[0] not in _GITHUB_RESERVED:
            return platform("subscription", f"{parts[0]}/{parts[1]} 发布", "github", "repo", f"{parts[0]}/{parts[1]}")
    if host == "youtube.com":
        m = re.search(r"(UC[\w-]{22})", url)
        if m:
            return platform("subscription", f"YouTube 频道 {m.group(1)}", "youtube", "user", m.group(1))
    if host == "reddit.com":
        m = re.match(r"^/r/([\w]+)", path)
        if m:
            return platform("subscription", f"r/{m.group(1)}", "reddit", "user", m.group(1))
    if host == "news.ycombinator.com" and path in {"", "/news", "/front"}:
        return platform("list", "Hacker News 首页", "hn", "ranking", "front")

    source_type, normalized, config = recognize_source_type(url)
    kind = "list" if source_type in (SourceType.DOUYIN_HOT, SourceType.ZHIHU) else "subscription"
    return {
        "kind": kind,
        "source_type": source_type.value,
        "url": normalized,
        "platform": (config or {}).get("platform"),
        "query": (config or {}).get("query"),
        "keyword": json.dumps(config, ensure_ascii=False) if config else None,
        "name": parsed.hostname or normalized,
    }
