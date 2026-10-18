"""B站适配器：投稿、搜索、热门 / 分区排行、评论、字幕（改造方案 3.2）。

公开接口需要 WBI 签名（``w_rid`` / ``wts``）和 ``buvid3`` Cookie，否则容易被风控（-352 / -412）。
签名密钥来自 ``/x/web-interface/nav`` 的 ``wbi_img``，缓存 1 小时。
"""

from __future__ import annotations

import base64
import hashlib
import time
import urllib.parse
from typing import Any, ClassVar

from .base import (
    COMMENTS,
    DEFAULT_UA,
    DETAIL,
    LIST_POSTS,
    RANKING,
    SEARCH,
    SUBTITLES,
    Comment,
    PlatformAdapter,
    PlatformError,
    SubtitleTrack,
    from_timestamp,
    https,
    parse_duration,
    strip_tags,
)

API = "https://api.bilibili.com"
_MIXIN_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]  # fmt: skip
_WBI_CACHE: dict[str, Any] = {"key": None, "at": 0.0}
_WBI_TTL = 3600
_FORBIDDEN = set("!'()*")


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode().rstrip("=")


# 投稿接口的浏览器指纹参数（缺失时返回 -352）
_DM_PARAMS = {
    "dm_img_list": "[]",
    "dm_img_str": _b64("WebGL 1.0 (OpenGL ES 2.0 Chromium)"),
    "dm_cover_img_str": _b64("ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)Google Inc. (Intel)"),
    "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
}


def mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in _MIXIN_TABLE if i < len(raw))[:32]


def sign_params(params: dict[str, Any], key: str, *, wts: int | None = None) -> dict[str, Any]:
    """WBI 签名：加 wts、按 key 排序、过滤 !'()* 后 md5(query + mixin_key)。"""
    signed = {k: "".join(ch for ch in str(v) if ch not in _FORBIDDEN) for k, v in params.items()}
    signed["wts"] = str(wts if wts is not None else int(time.time()))
    query = urllib.parse.urlencode(sorted(signed.items()))
    signed["w_rid"] = hashlib.md5((query + key).encode()).hexdigest()  # noqa: S324 — 平台协议要求
    return signed


def _key_from_url(url: str) -> str:
    return url.rsplit("/", 1)[-1].split(".", 1)[0]


class BilibiliAdapter(PlatformAdapter):
    platform = "bilibili"
    label = "B站"
    capabilities: ClassVar[frozenset[str]] = frozenset({LIST_POSTS, SEARCH, RANKING, DETAIL, COMMENTS, SUBTITLES})
    headers: ClassVar[dict[str, str]] = {"Referer": "https://www.bilibili.com/", "Origin": "https://www.bilibili.com"}

    async def _ensure_cookie(self) -> None:
        if any(c.name == "buvid3" for c in self.client.cookies.jar):
            return
        try:  # 先访问首页拿 buvid3 / b_nut，和浏览器首次访问一致，降低风控概率
            await self.client.get("https://www.bilibili.com/", headers={"User-Agent": DEFAULT_UA})
            if any(c.name == "buvid3" for c in self.client.cookies.jar):
                return
        except Exception:
            pass
        try:
            data = await self._get_json(f"{API}/x/frontend/finger/spi", headers=self.headers)
            buvid = (data.get("data") or {}).get("b_3")
            if buvid:
                self.client.cookies.set("buvid3", buvid, domain=".bilibili.com")
        except Exception:  # 拿不到也继续，部分接口不需要
            pass

    async def _wbi_key(self) -> str:
        now = time.time()
        if _WBI_CACHE["key"] and now - _WBI_CACHE["at"] < _WBI_TTL:
            return _WBI_CACHE["key"]
        data = await self._get_json(f"{API}/x/web-interface/nav", headers=self.headers)
        img = ((data.get("data") or {}).get("wbi_img")) or {}
        if not img.get("img_url") or not img.get("sub_url"):
            raise PlatformError("B站签名密钥获取失败，接口可能已变更")
        key = mixin_key(_key_from_url(img["img_url"]), _key_from_url(img["sub_url"]))
        _WBI_CACHE.update(key=key, at=now)
        return key

    async def _api(self, path: str, params: dict[str, Any], *, wbi: bool = False) -> Any:
        await self._ensure_cookie()
        if wbi:
            params = sign_params(params, await self._wbi_key())
        data = await self._get_json(f"{API}{path}", params=params, headers=self.headers)
        code = data.get("code", 0)
        if code in (-352, -412, -509, -799):
            raise PlatformError(f"B站风控拦截（{code}），稍后自动重试")
        if code != 0:
            raise PlatformError(f"B站接口错误 {code}：{data.get('message') or ''}".strip())
        payload = data.get("data") or {}
        if isinstance(payload, dict) and payload.get("v_voucher") and len(payload) == 1:
            raise PlatformError("B站风控拦截（需要验证），稍后自动重试")
        return payload

    # ── 条目转换 ──

    def to_entry(self, v: dict[str, Any]) -> dict[str, Any]:
        stat = v.get("stat") or {}
        owner = v.get("owner") or {}
        bvid = v.get("bvid") or ""
        mid = owner.get("mid") or v.get("mid")
        metrics = {
            "views": stat.get("view", v.get("play")),
            "likes": stat.get("like", v.get("like")),
            "coins": stat.get("coin"),
            "favorites": stat.get("favorite", v.get("favorites")),
            "comments": stat.get("reply", v.get("comment", v.get("review"))),
            "danmaku": stat.get("danmaku", v.get("video_review")),
            "shares": stat.get("share"),
        }
        metrics = {k: val for k, val in metrics.items() if isinstance(val, int | float) and val >= 0}
        duration = parse_duration(v.get("duration") or v.get("length"))
        dim = v.get("dimension") or {}
        orientation = None
        if dim.get("width") and dim.get("height"):
            w, h = (dim["height"], dim["width"]) if dim.get("rotate") else (dim["width"], dim["height"])
            orientation = "portrait" if h > w else "landscape"
        return {
            "title": strip_tags(v.get("title")),
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else v.get("arcurl") or "",
            "summary": strip_tags(v.get("desc") or v.get("description")) or None,
            "author": owner.get("name") or v.get("author"),
            "author_id": str(mid) if mid else None,
            "author_url": f"https://space.bilibili.com/{mid}" if mid else None,
            "published_at": from_timestamp(v.get("pubdate") or v.get("created") or v.get("senddate")),
            "cover_url": https(v.get("pic")),
            "platform": self.platform,
            "media_type": "video",
            "platform_item_id": bvid or (str(v.get("aid")) if v.get("aid") else None),
            "media": {
                k: val
                for k, val in {"duration": duration, "orientation": orientation, "aid": v.get("aid")}.items()
                if val
            },
            "metrics": metrics,
            "tags": [t for t in str(v.get("tag") or "").split(",") if t][:5],
        }

    # ── 能力 ──

    supports_paging: ClassVar[bool] = True

    async def list_posts(self, target: str, *, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        """UP 主投稿。主接口需要浏览器指纹参数（dm_*）；仍被风控时退到合集接口。"""
        params = {
            "mid": target,
            "ps": min(limit, 30),
            "pn": page,
            "order": "pubdate",
            "platform": "web",
            "web_location": "1550101",
            **_DM_PARAMS,
        }
        try:
            data = await self._api("/x/space/wbi/arc/search", params, wbi=True)
            vlist = ((data.get("list") or {}).get("vlist")) or []
        except PlatformError as exc:
            if "风控" not in str(exc):
                raise
            data = await self._api(
                "/x/series/recArchivesByKeywords", {"mid": target, "keywords": "", "ps": min(limit, 30)}
            )
            vlist = [{**v, "mid": v.get("upMid") or target} for v in data.get("archives") or []]
        return [self.to_entry(v) for v in vlist[:limit]]

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._api(
            "/x/web-interface/wbi/search/type",
            {"search_type": "video", "keyword": query, "page": 1, "order": "pubdate"},
            wbi=True,
        )
        return [self.to_entry(v) for v in (data.get("result") or [])[:limit] if v.get("type", "video") == "video"]

    async def list_ranking(self, name: str = "", *, limit: int = 30) -> list[dict[str, Any]]:
        """``popular``（综合热门，默认）或分区 id（如 ``36`` 知识、``188`` 科技）的排行。"""
        if not name or name == "popular":
            data = await self._api("/x/web-interface/popular", {"ps": min(limit, 50), "pn": 1})
            items = data.get("list") or []
        else:
            data = await self._api("/x/web-interface/ranking/v2", {"rid": name, "type": "all"})
            items = data.get("list") or []
        entries = []
        for rank, v in enumerate(items[:limit], start=1):
            entry = self.to_entry(v)
            entry["metrics"]["rank"] = rank
            entries.append(entry)
        return entries

    async def fetch_detail(self, item_id: str) -> dict[str, Any]:
        key = "bvid" if item_id.upper().startswith("BV") else "aid"
        data = await self._api("/x/web-interface/view", {key: item_id})
        entry = self.to_entry(data)
        entry["media"]["cid"] = data.get("cid")
        return entry

    async def fetch_comments(self, item_id: str, *, limit: int = 20) -> list[Comment]:
        aid = item_id
        if item_id.upper().startswith("BV"):
            aid = str((await self._api("/x/web-interface/view", {"bvid": item_id})).get("aid"))
        data = await self._api("/x/v2/reply/main", {"oid": aid, "type": 1, "mode": 3, "next": 0})  # mode=3 按热度
        out = []
        for r in (data.get("replies") or [])[:limit]:
            out.append(
                Comment(
                    text=((r.get("content") or {}).get("message") or "").strip(),
                    author=(r.get("member") or {}).get("uname"),
                    likes=r.get("like"),
                    replies=r.get("rcount"),
                    published_at=from_timestamp(r.get("ctime")),
                )
            )
        return out

    async def fetch_subtitles(self, item_id: str) -> list[SubtitleTrack]:
        view = await self._api("/x/web-interface/view", {"bvid": item_id})
        data = await self._api("/x/player/wbi/v2", {"bvid": item_id, "cid": view.get("cid")}, wbi=True)
        tracks = []
        for sub in ((data.get("subtitle") or {}).get("subtitles")) or []:
            url = https(sub.get("subtitle_url"))
            if not url:
                continue
            body = await self._get_json(url, headers=self.headers)
            segments = [
                {"from": s.get("from"), "to": s.get("to"), "text": s.get("content")} for s in body.get("body") or []
            ]
            tracks.append(
                SubtitleTrack(
                    language=sub.get("lan") or "zh",
                    text="\n".join(s["text"] or "" for s in segments),
                    segments=segments,
                )
            )
        return tracks
