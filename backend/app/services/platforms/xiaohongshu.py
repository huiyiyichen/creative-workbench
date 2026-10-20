"""小红书（改造方案 3.2）：本机浏览器 + 采集账号登录态，低频。

* 订阅：``platform://xiaohongshu/user/<user_id>`` → ``/api/sns/web/v1/user_posted``
* 搜索：``https://www.xiaohongshu.com/search_result?keyword=<词>`` → ``/api/sns/web/v1/search/notes``
* 详情：笔记页 → ``/api/sns/web/v1/feed``，没有时读页面 ``window.__INITIAL_STATE__``
* 评论：笔记页 → ``/api/sns/web/v2/comment/page``，取前 N 条，不取回复。

笔记链接需要带 ``xsec_token``（列表接口给出），所以条目的 url 里保留它；只有 id 时退回 explore 链接。
"""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import parse_qs, quote, urlparse

from . import browser
from .base import COMMENTS, DETAIL, LIST_POSTS, SEARCH, Comment, PlatformAdapter, PlatformError, from_timestamp, https

STATE_SCRIPT = (
    "() => { try { return JSON.parse(JSON.stringify(window.__INITIAL_STATE__ || null)); } catch (e) { return null; } }"
)


def _count(v: Any) -> int | None:
    """'1.2万' / '3456' / 12 → 整数。"""
    if v is None or v == "":
        return None
    if isinstance(v, int | float):
        return int(v)
    s = str(v).strip().replace(",", "")
    mult = 1
    if s.endswith(("万", "w", "W")):
        mult, s = 10000, s[:-1]
    elif s.endswith(("千", "k", "K")):
        mult, s = 1000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def note_url(note_id: str, token: str | None, source: str = "pc_feed") -> str:
    if token:
        return f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={quote(token)}&xsec_source={source}"
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def split_ref(item_id: str) -> tuple[str, str | None]:
    """平台 id 可以是「笔记 id」或带 token 的完整链接。"""
    if item_id.startswith("http"):
        u = urlparse(item_id)
        token = (parse_qs(u.query).get("xsec_token") or [None])[0]
        return u.path.rstrip("/").rsplit("/", 1)[-1], token
    nid, _, token = item_id.partition("|")
    return nid, token or None


def to_entry(note: dict[str, Any], token: str | None = None) -> dict[str, Any] | None:
    card = note.get("note_card") or note
    nid = str(note.get("id") or note.get("note_id") or card.get("note_id") or "")
    if not nid:
        return None
    token = token or note.get("xsec_token") or card.get("xsec_token")
    user = card.get("user") or {}
    inter = card.get("interact_info") or {}
    cover = card.get("cover") or {}
    images = card.get("image_list") or []
    title = (card.get("display_title") or card.get("title") or "").strip()
    desc = (card.get("desc") or "").strip()
    is_video = (card.get("type") or "") == "video"
    w, h = cover.get("width"), cover.get("height")
    cover_url = (
        cover.get("url_default") or cover.get("url") or ((images[0] or {}).get("url_default") if images else None)
    )
    metrics = {
        "likes": _count(inter.get("liked_count")),
        "favorites": _count(inter.get("collected_count")),
        "comments": _count(inter.get("comment_count")),
        "shares": _count(inter.get("share_count")),
    }
    uid = user.get("user_id") or user.get("userId")
    return {
        "title": (title or desc.split("\n")[0] or f"小红书笔记 {nid}")[:300],
        "url": note_url(nid, token),
        "summary": desc or None,
        "author": user.get("nickname") or user.get("nick_name"),
        "author_id": uid,
        "author_url": f"https://www.xiaohongshu.com/user/profile/{uid}" if uid else None,
        "published_at": from_timestamp((card.get("time") or 0) / 1000) if card.get("time") else None,
        "cover_url": https(cover_url),
        "platform": "xiaohongshu",
        "media_type": "video" if is_video else "image",
        "platform_item_id": nid,
        "media": {
            k: v
            for k, v in {
                "orientation": ("portrait" if h > w else "landscape") if w and h else "portrait",
                "images": len(images) or None,
                "xsec_token": token,
            }.items()
            if v
        },
        "metrics": {k: v for k, v in metrics.items() if v is not None},
        "tags": [t.get("name") for t in card.get("tag_list") or [] if t.get("name")][:8],
    }


def notes_from(payload: Any) -> list[dict[str, Any]]:
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    raw = data.get("notes") or data.get("items") or []
    out, seen = [], set()
    for n in raw:
        if not isinstance(n, dict):
            continue
        if n.get("model_type") not in (None, "note"):
            continue
        e = to_entry(n)
        if e and e["platform_item_id"] not in seen:
            seen.add(e["platform_item_id"])
            out.append(e)
    return out


def detail_from_state(state: Any, note_id: str, token: str | None) -> dict[str, Any] | None:
    try:
        m = state["note"]["noteDetailMap"][note_id]["note"]
    except (KeyError, TypeError):
        return None
    m = {
        **m,
        "note_id": note_id,
        "display_title": m.get("title"),
        "interact_info": {
            "liked_count": (m.get("interactInfo") or {}).get("likedCount"),
            "collected_count": (m.get("interactInfo") or {}).get("collectedCount"),
            "comment_count": (m.get("interactInfo") or {}).get("commentCount"),
            "share_count": (m.get("interactInfo") or {}).get("shareCount"),
        },
        "image_list": [{"url_default": i.get("urlDefault")} for i in m.get("imageList") or []],
        "user": {"user_id": (m.get("user") or {}).get("userId"), "nickname": (m.get("user") or {}).get("nickname")},
    }
    if m["image_list"]:
        m["cover"] = {"url_default": m["image_list"][0]["url_default"]}
    return to_entry(m, token)


def comments_from(payload: Any, limit: int) -> list[Comment]:
    data = (payload or {}).get("data") or {} if isinstance(payload, dict) else {}
    out = []
    for c in data.get("comments") or []:
        text = (c.get("content") or "").strip()
        if not text:
            continue
        out.append(
            Comment(
                text=text,
                author=(c.get("user_info") or {}).get("nickname"),
                likes=_count(c.get("like_count")),
                replies=_count(c.get("sub_comment_count")),
                published_at=from_timestamp((c.get("create_time") or 0) / 1000) if c.get("create_time") else None,
                id=str(c["id"]) if c.get("id") else None,
            )
        )
    return out[:limit]


class XiaohongshuAdapter(PlatformAdapter):
    platform: ClassVar[str] = "xiaohongshu"
    label: ClassVar[str] = "小红书"
    capabilities: ClassVar[frozenset[str]] = frozenset({LIST_POSTS, SEARCH, DETAIL, COMMENTS})
    browser_based: ClassVar[bool] = True

    async def list_posts(self, target: str, *, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        mode, _, uid = target.partition("/") if "/" in target else ("user", "", target)
        if mode != "user" or not uid:
            raise PlatformError("小红书订阅地址应为 platform://xiaohongshu/user/<user_id>")
        cap = await browser.BROWSER.capture(
            "xiaohongshu",
            f"https://www.xiaohongshu.com/user/profile/{uid}",
            {"posts": "/api/sns/web/v1/user_posted"},
        )
        items: list[dict[str, Any]] = []
        for payload in cap.responses.get("posts") or []:
            items.extend(notes_from(payload))
        return items[:limit]

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        cap = await browser.BROWSER.capture(
            "xiaohongshu",
            f"https://www.xiaohongshu.com/search_result?keyword={quote(query)}&source=web_search_result_notes",
            {"notes": "/api/sns/web/v1/search/notes"},
        )
        items: list[dict[str, Any]] = []
        for payload in cap.responses.get("notes") or []:
            items.extend(notes_from(payload))
        return items[:limit]

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        nid, token = split_ref(item_id)
        cap = await browser.BROWSER.capture(
            "xiaohongshu",
            note_url(nid, token),
            {"feed": "/api/sns/web/v1/feed"},
            wait_seconds=12,
            state_script=STATE_SCRIPT,
        )
        found = notes_from(cap.first("feed")) if cap.first("feed") else []
        if not found:
            e = detail_from_state(cap.page_state, nid, token)
            found = [e] if e else []
        if not found:
            raise PlatformError("小红书笔记详情读取失败（可能需要 xsec_token 或登录）")
        return found[0]

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        nid, token = split_ref(item_id)
        cap = await browser.BROWSER.capture(
            "xiaohongshu", note_url(nid, token), {"comments": "/api/sns/web/v2/comment/page"}, scroll=1
        )
        out: list[Comment] = []
        for payload in cap.responses.get("comments") or []:
            out.extend(comments_from(payload, limit))
        out.sort(key=lambda c: -(c.likes or 0))
        return out[:limit]
