"""灵感库（改造方案 6.1–6.5、6.7、6.9）。

收进来的方式：一键收藏（来自采集内容）、粘贴链接、浏览器扩展（图片 / 链接 / 选中文字）、剪贴板、本地文件、
素材收件箱、从内容取图（文章配图、视频截帧）、外部生成图（读 PNG 元数据）。收藏时不选类别。
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_observation import MediaAsset
from app.models.library import (
    ImportMethod,
    LibraryBoard,
    LibraryBoardItem,
    LibraryItem,
    LibraryKind,
    LibraryLink,
    License,
    LinkRelation,
    Note,
)
from app.services import library_files
from app.services.event_members import event_members_subquery

logger = logging.getLogger(__name__)
_em = event_members_subquery()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

MEDIA_TO_KIND = {
    "article": LibraryKind.ARTICLE,
    "video": LibraryKind.VIDEO,
    "image": LibraryKind.IMAGE_TEXT,
    "post": LibraryKind.POST,
    "prompt": LibraryKind.PROMPT,
    "repo": LibraryKind.REPO,
}


def json_has(col, value: str):
    """JSON 列（字符串数组）里有没有这个值。序列化默认 ensure_ascii，中文是 \\uXXXX；
    用 ``!`` 作 LIKE 转义符，让反斜杠在 PostgreSQL 和 SQLite 里都按字面匹配。"""
    import json as _json

    needle = _json.dumps(str(value)).replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return cast(col, Text).like(f"%{needle}%", escape="!")


def json_text_like(col, term: str):
    """JSON 列的文本里包含 ``term``（子串，中文按 \\uXXXX 转义后匹配）。"""
    import json as _json

    needle = _json.dumps(str(term))[1:-1].replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return cast(col, Text).like(f"%{needle}%", escape="!")


class LibraryError(ValueError):
    pass


class LibraryNotFoundError(LookupError):
    pass


# ── 链接识别 ─────────────────────────────────────────────────────


def parse_link(url: str) -> tuple[str, str | None]:
    """返回 (平台, 条目 id)。识别 B站、抖音、小红书、YouTube、GitHub、HN、Reddit，其余为网页。"""
    u = urlparse(url.strip())
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = u.path or ""
    if host.endswith("bilibili.com") or host == "b23.tv":
        m = re.search(r"(BV[0-9A-Za-z]{10})", url)
        return "bilibili", m.group(1) if m else None
    if host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com"):
        if host == "youtu.be":
            return "youtube", path.strip("/").split("/")[0] or None
        vid = parse_qs(u.query).get("v", [None])[0]
        if not vid:
            m = re.match(r"/(shorts|embed|live)/([\w-]{6,})", path)
            vid = m.group(2) if m else None
        return "youtube", vid
    if host == "github.com":
        parts = [p for p in path.split("/") if p]
        return "github", "/".join(parts[:2]) if len(parts) >= 2 else None
    if host == "news.ycombinator.com":
        return "hn", parse_qs(u.query).get("id", [None])[0]
    if host.endswith("reddit.com"):
        return "reddit", None
    if host.endswith("douyin.com"):
        m = re.search(r"/video/(\d+)", path)
        return "douyin", m.group(1) if m else None
    if host.endswith("xiaohongshu.com") or host == "xhslink.com":
        m = re.search(r"/(?:explore|discovery/item)/([0-9a-f]+)", path)
        return "xiaohongshu", m.group(1) if m else None
    return "web", None


PROMPT_PATTERNS = [
    re.compile(r"(?:提示词|prompt)\s*[:：]\s*[\"“「]?(.{12,600}?)[\"”」]?(?:\n\n|$)", re.I | re.S),
]
REPO_PATTERN = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)")


def extract_prompts_and_repos(text: str | None) -> tuple[list[str], list[str]]:
    """从视频描述或网页中提取提示词和仓库链接（6.1），作为独立条目。"""
    if not text:
        return [], []
    prompts: list[str] = []
    for pat in PROMPT_PATTERNS:
        for m in pat.finditer(text):
            p = m.group(1).strip()
            if p and p not in prompts:
                prompts.append(p)
    repos: list[str] = []
    for m in REPO_PATTERN.finditer(text):
        name = m.group(1).rstrip(".")
        if name.count("/") == 1 and name not in repos:
            repos.append(name)
    return prompts[:5], repos[:10]


def _og(html: str) -> dict[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {}
    for prop in ("og:title", "og:description", "og:image", "og:site_name", "twitter:image", "author", "description"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            out[prop] = str(tag["content"]).strip()
    if soup.title and soup.title.string:
        out.setdefault("title", soup.title.string.strip())
    return out


async def fetch_link_meta(
    url: str, platform: str, item_id: str | None, *, api_keys: dict[str, str] | None = None
) -> dict[str, Any]:
    """拉取标题、封面、作者、指标。平台有适配器的走适配器，其余读网页 meta。失败时只保留链接。"""
    from app.services.platforms import ADAPTERS, DETAIL, get_adapter

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": UA}) as client:
        if item_id and platform in ADAPTERS and DETAIL in ADAPTERS[platform].capabilities:
            try:
                adapter = get_adapter(platform, client, api_key=(api_keys or {}).get(platform))
                entry = await adapter.fetch_detail(item_id)
                if entry and entry.get("title"):
                    return entry
            except Exception as exc:  # noqa: BLE001 — 平台失败回退到网页 meta
                logger.info("library link detail via %s failed: %s", platform, exc)
        if platform == "youtube" and item_id:
            try:
                r = await client.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"})
                if r.status_code == 200:
                    d = r.json()
                    return {
                        "title": d.get("title"),
                        "author": d.get("author_name"),
                        "cover_url": d.get("thumbnail_url"),
                        "media_type": "video",
                        "platform": "youtube",
                    }
            except (httpx.HTTPError, ValueError):
                pass
        try:
            r = await client.get(url)
            if r.status_code < 400 and "html" in r.headers.get("content-type", ""):
                og = _og(r.text)
                return {
                    "title": og.get("og:title") or og.get("title"),
                    "summary": og.get("og:description") or og.get("description"),
                    "cover_url": og.get("og:image") or og.get("twitter:image"),
                    "author": og.get("author") or og.get("og:site_name"),
                }
        except httpx.HTTPError as exc:
            logger.info("library link fetch failed: %s", exc)
    return {}


# ── 条目 ─────────────────────────────────────────────────────────


def _add_link(
    db: AsyncSession, a: tuple[str, int], b: tuple[str, int], relation: str, weight: float | None = None
) -> None:
    db.add(LibraryLink(from_type=a[0], from_id=a[1], to_type=b[0], to_id=b[1], relation=relation, weight=weight))


async def ensure_link(
    db: AsyncSession, a: tuple[str, int], b: tuple[str, int], relation: str, weight: float | None = None
) -> None:
    exists = (
        await db.execute(
            select(LibraryLink.id).where(
                LibraryLink.from_type == a[0],
                LibraryLink.from_id == a[1],
                LibraryLink.to_type == b[0],
                LibraryLink.to_id == b[1],
                LibraryLink.relation == relation,
            )
        )
    ).first()
    if not exists:
        _add_link(db, a, b, relation, weight)


async def _existing(db: AsyncSession, *, content_id: int | None = None, url: str | None = None, sha: str | None = None):
    stmt = select(LibraryItem).where(LibraryItem.archived_at.is_(None))
    if content_id:
        stmt = stmt.where(LibraryItem.content_id == content_id)
    elif sha:
        stmt = stmt.where(LibraryItem.file_sha256 == sha)
    elif url:
        stmt = stmt.where(LibraryItem.url == url)
    else:
        return None
    return (await db.execute(stmt.limit(1))).scalar_one_or_none()


async def _extract_children(db: AsyncSession, parent: LibraryItem, text: str | None) -> list[LibraryItem]:
    prompts, repos = extract_prompts_and_repos(text)
    children: list[LibraryItem] = []
    for p in prompts:
        child = LibraryItem(
            kind=LibraryKind.PROMPT.value,
            title=p[:60],
            body=p,
            source_url=parent.url,
            import_method=ImportMethod.EXTRACTED.value,
            license=License.UNKNOWN.value,
        )
        db.add(child)
        children.append(child)
    for name in repos:
        url = f"https://github.com/{name}"
        if await _existing(db, url=url):
            continue
        child = LibraryItem(
            kind=LibraryKind.REPO.value,
            title=name,
            url=url,
            platform="github",
            source_url=parent.url,
            import_method=ImportMethod.EXTRACTED.value,
        )
        db.add(child)
        children.append(child)
    await db.flush()
    for child in children:
        await ensure_link(db, ("item", parent.id), ("item", child.id), LinkRelation.EXTRACTED.value)
    return children


async def add_from_content(
    db: AsyncSession, content_id: int, *, method: str = ImportMethod.FAVORITE.value
) -> LibraryItem:
    """一键收藏：今日、热点、专题、条目详情。同一条内容只收一次。"""
    content = await db.get(ContentItem, content_id)
    if content is None:
        raise LibraryNotFoundError(f"content {content_id} not found")
    existing = await _existing(db, content_id=content_id)
    if existing is not None:
        return existing
    media = content.media or {}
    thumb = None
    if content.cover_asset_id:
        asset = await db.get(MediaAsset, content.cover_asset_id)
        if asset is not None and asset.status == "ready":
            thumb = asset
    item = LibraryItem(
        kind=MEDIA_TO_KIND.get(content.media_type or "article", LibraryKind.ARTICLE).value,
        title=content.title,
        url=content.url,
        platform=content.platform,
        author=content.author,
        content_id=content.id,
        body=content.summary,
        meta={
            k: v for k, v in {"duration": media.get("duration"), "orientation": media.get("orientation")}.items() if v
        },
        cover_url=content.cover_url,
        dominant_color=thumb.dominant_color if thumb else None,
        width=thumb.width if thumb else None,
        height=thumb.height if thumb else None,
        import_method=method,
        tags=list((content.tags or {}).keys())[:10] if isinstance(content.tags, dict) else (content.tags or None),
    )
    db.add(item)
    content.is_favorited = True
    await db.flush()
    await _extract_children(db, item, "\n".join(filter(None, [content.summary, content.raw_content])))
    from app.services.content_journey import record_journey

    await record_journey(db, content.id, "favorited", f"收进灵感库（#{item.id}）", detail={"library_item_id": item.id})
    await db.commit()
    await db.refresh(item)
    return item


async def add_from_link(
    db: AsyncSession, url: str, *, method: str = ImportMethod.LINK.value, note: str | None = None
) -> LibraryItem:
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise LibraryError("请粘贴以 http(s):// 开头的链接")
    content = (await db.execute(select(ContentItem).where(ContentItem.url == url).limit(1))).scalar_one_or_none()
    if content is not None:
        return await add_from_content(db, content.id, method=method)
    existing = await _existing(db, url=url)
    if existing is not None:
        return existing
    platform, item_id = parse_link(url)
    from app.services.platform_keys import get_platform_keys

    meta = await fetch_link_meta(url, platform, item_id, api_keys=await get_platform_keys(db))
    media_type = meta.get("media_type") or {
        "bilibili": "video",
        "youtube": "video",
        "douyin": "video",
        "github": "repo",
        "xiaohongshu": "image",
    }.get(platform)
    kind = MEDIA_TO_KIND.get(media_type or "", LibraryKind.LINK).value
    extra: dict[str, Any] = {}
    metrics = meta.get("metrics") or {}
    if metrics:
        extra["metrics"] = metrics
    for k in ("language", "duration", "orientation"):
        if (meta.get("media") or {}).get(k) or meta.get(k):
            extra[k] = (meta.get("media") or {}).get(k) or meta.get(k)
    item = LibraryItem(
        kind=kind,
        title=(meta.get("title") or url)[:500],
        url=url,
        platform=None if platform == "web" else platform,
        author=meta.get("author"),
        body=meta.get("summary") or meta.get("description"),
        cover_url=meta.get("cover_url"),
        meta=extra or None,
        import_method=method,
        my_notes=note,
    )
    db.add(item)
    await db.flush()
    await _extract_children(db, item, item.body)
    await db.commit()
    await db.refresh(item)
    return item


async def add_file(
    db: AsyncSession,
    content: bytes,
    filename: str,
    *,
    mime: str | None = None,
    method: str = ImportMethod.FILE.value,
    title: str | None = None,
    source_url: str | None = None,
    license: str | None = None,
) -> LibraryItem:
    """图片、视频片段、音频、字体、配色文件。按 sha256 去重；生成图读出提示词与参数，授权默认「AI 生成」。"""
    try:
        sf = library_files.store_bytes(content, filename, mime)
    except library_files.LibraryFileError as exc:
        raise LibraryError(str(exc)) from exc
    existing = await _existing(db, sha=sf.sha256)
    if existing is not None:
        return existing
    asset_kind = sf.asset_kind if sf.asset_kind != "file" else None
    kind = LibraryKind.GENERATED.value if sf.generated else LibraryKind.ASSET.value
    meta = dict(sf.meta)
    if sf.palette and asset_kind == "palette":
        meta["colors"] = sf.palette
    item = LibraryItem(
        kind=kind,
        asset_kind=asset_kind,
        title=(title or meta.get("family") or sf.name)[:500],
        body=meta.get("prompt"),
        meta=meta or None,
        file_sha256=sf.sha256,
        file_path=sf.path,
        file_name=sf.name,
        mime=sf.mime,
        bytes=sf.bytes,
        thumb_small=sf.thumb_small,
        thumb_large=sf.thumb_large,
        width=sf.width,
        height=sf.height,
        duration=sf.duration,
        dominant_color=sf.dominant_color,
        palette=sf.palette,
        license=license or (License.AI.value if sf.generated else License.UNKNOWN.value),
        import_method=method,
        source_url=source_url,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def add_text(
    db: AsyncSession,
    text: str,
    *,
    kind: str = "prompt",
    title: str | None = None,
    source_url: str | None = None,
    method: str = ImportMethod.EXTENSION.value,
) -> LibraryItem:
    """选中文字 / 提示词。"""
    text = (text or "").strip()
    if not text:
        raise LibraryError("内容为空")
    if kind not in (LibraryKind.PROMPT.value, LibraryKind.LINK.value, LibraryKind.ARTICLE.value):
        kind = LibraryKind.PROMPT.value
    item = LibraryItem(
        kind=kind,
        title=(title or text[:60]).strip()[:500],
        body=text,
        source_url=source_url,
        url=source_url if kind != "prompt" else None,
        import_method=method,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def add_frame_from_content(db: AsyncSession, content_id: int, image_url: str | None = None) -> LibraryItem:
    """从内容取图：文章配图（给出图片地址）或封面。视频截帧需本地视频文件，在 ``add_video_frame``。"""
    content = await db.get(ContentItem, content_id)
    if content is None:
        raise LibraryNotFoundError(f"content {content_id} not found")
    src = image_url or content.cover_url
    if not src:
        raise LibraryError("这条内容没有可取的图片")
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers={"User-Agent": UA, "Referer": content.url}
    ) as client:
        r = await client.get(src)
    if r.status_code >= 400:
        raise LibraryError(f"取图失败：HTTP {r.status_code}")
    name = urlparse(src).path.rsplit("/", 1)[-1] or "image.jpg"
    item = await add_file(
        db,
        r.content,
        name,
        mime=r.headers.get("content-type"),
        method=ImportMethod.FRAME.value,
        title=f"{content.title[:60]} · 配图",
        source_url=content.url,
    )
    await ensure_link(db, ("content", content_id), ("item", item.id), LinkRelation.EXTRACTED.value)
    await db.commit()
    return item


async def add_video_frame(db: AsyncSession, item_id: int, at: float) -> LibraryItem:
    """视频片段截帧（指定时间点，秒）。"""
    src = await get_item_model(db, item_id)
    if not src.file_path or src.asset_kind != "motion":
        raise LibraryError("只有灵感库里的视频片段可以截帧")
    png = library_files.video_frame_at(src.file_path, at)
    if png is None:
        raise LibraryError("截帧失败（需要 ffmpeg）")
    item = await add_file(
        db,
        png,
        f"{src.file_sha256}-{at:.1f}s.png",
        mime="image/png",
        method=ImportMethod.FRAME.value,
        title=f"{src.title} · {at:.1f}s",
    )
    await ensure_link(db, ("item", src.id), ("item", item.id), LinkRelation.EXTRACTED.value)
    await db.commit()
    return item


async def get_item_model(db: AsyncSession, item_id: int) -> LibraryItem:
    item = await db.get(LibraryItem, item_id)
    if item is None or item.archived_at is not None:
        raise LibraryNotFoundError(f"library item {item_id} not found")
    return item


EDITABLE = {"title", "tags", "license", "my_notes", "starred", "body", "meta", "asset_kind", "kind"}


async def update_item(db: AsyncSession, item_id: int, values: dict[str, Any]) -> LibraryItem:
    item = await get_item_model(db, item_id)
    for k, v in values.items():
        if k not in EDITABLE:
            continue
        if k == "license" and v not in {x.value for x in License}:
            raise LibraryError("授权状态无效")
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


async def bulk_license(db: AsyncSession, ids: list[int], license: str) -> int:
    if license not in {x.value for x in License}:
        raise LibraryError("授权状态无效")
    rows = (await db.execute(select(LibraryItem).where(LibraryItem.id.in_(ids)))).scalars().all()
    for r in rows:
        r.license = license
    await db.commit()
    return len(rows)


async def archive_item(db: AsyncSession, item_id: int) -> None:
    item = await get_item_model(db, item_id)
    item.archived_at = datetime.now(UTC)
    if item.content_id:
        content = await db.get(ContentItem, item.content_id)
        if content is not None:
            others = (
                await db.execute(
                    select(func.count()).where(
                        LibraryItem.content_id == item.content_id,
                        LibraryItem.archived_at.is_(None),
                        LibraryItem.id != item.id,
                    )
                )
            ).scalar()
            if not others:
                content.is_favorited = False
    await db.commit()


# ── 列表与搜索 ───────────────────────────────────────────────────


def _terms(q: str) -> list[str]:
    import jieba

    q = q.strip()
    words = [w.strip() for w in jieba.cut_for_search(q) if w.strip() and len(w.strip()) >= 1]
    # 英文 / 数字串保持整体；中文按词；去掉单字虚词
    stop = set("的了是在和与及或也都就把被")
    return list(dict.fromkeys(w for w in words if w not in stop)) or [q]


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def color_distance(a: str, b: str) -> float:
    (r1, g1, b1), (r2, g2, b2) = _hex_rgb(a), _hex_rgb(b)
    rm = (r1 + r2) / 2
    return ((2 + rm / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - rm) / 256) * (b1 - b2) ** 2) ** 0.5


def item_view(item: LibraryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "asset_kind": item.asset_kind,
        "title": item.title,
        "url": item.url,
        "platform": item.platform,
        "author": item.author,
        "content_id": item.content_id,
        "body": item.body,
        "meta": item.meta,
        "file_name": item.file_name,
        "mime": item.mime,
        "bytes": item.bytes,
        "has_file": bool(item.file_path),
        "thumb": bool(item.thumb_small),
        "width": item.width,
        "height": item.height,
        "duration": item.duration,
        "dominant_color": item.dominant_color,
        "palette": item.palette,
        "cover_url": item.cover_url,
        "license": item.license,
        "import_method": item.import_method,
        "source_url": item.source_url,
        "tags": item.tags or [],
        "ai_tags": item.ai_tags or [],
        "ai_description": item.ai_description,
        "my_notes": item.my_notes,
        "starred": item.starred,
        "obsidian_path": item.obsidian_path,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


async def list_items(
    db: AsyncSession,
    *,
    kind: str | None = None,
    asset_kind: str | None = None,
    platform: str | None = None,
    license: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    color: str | None = None,
    board_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    stmt = select(LibraryItem).where(LibraryItem.archived_at.is_(None))
    if kind == "asset":
        stmt = stmt.where(LibraryItem.kind.in_(("asset", "generated")))
    elif kind:
        stmt = stmt.where(LibraryItem.kind == kind)
    if asset_kind:
        stmt = stmt.where(LibraryItem.asset_kind == asset_kind)
    if platform:
        stmt = stmt.where(LibraryItem.platform == platform)
    if license:
        stmt = stmt.where(LibraryItem.license == license)
    if tag:
        stmt = stmt.where(or_(json_has(LibraryItem.tags, tag), json_has(LibraryItem.ai_tags, tag)))
    if since:
        stmt = stmt.where(LibraryItem.created_at >= since)
    if until:
        stmt = stmt.where(LibraryItem.created_at < until)
    if board_id:
        stmt = stmt.join(LibraryBoardItem, LibraryBoardItem.item_id == LibraryItem.id).where(
            LibraryBoardItem.board_id == board_id
        )
    if q:
        for term in _terms(q):
            like = f"%{term}%"
            stmt = stmt.where(
                or_(
                    LibraryItem.title.ilike(like),
                    LibraryItem.body.ilike(like),
                    LibraryItem.ai_description.ilike(like),
                    LibraryItem.author.ilike(like),
                    json_text_like(LibraryItem.tags, term),
                    json_text_like(LibraryItem.ai_tags, term),
                    LibraryItem.my_notes.ilike(like),
                )
            )
    if color:
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", color):
            raise LibraryError("颜色格式应为 #rrggbb")
        color = "#" + color.lstrip("#").lower()
        rows = (await db.execute(stmt.where(LibraryItem.palette.is_not(None)).limit(2000))).scalars().all()
        scored = sorted(
            ((min(color_distance(color, c) for c in (r.palette or [r.dominant_color]) if c), r) for r in rows),
            key=lambda x: x[0],
        )
        hits = [r for d, r in scored if d < 160]
        return {"total": len(hits), "items": [item_view(r) for r in hits[offset : offset + limit]]}
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (
        (
            await db.execute(
                stmt.order_by(LibraryItem.created_at.desc(), LibraryItem.id.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {"total": total, "items": [item_view(r) for r in rows]}


async def facets(db: AsyncSession) -> dict[str, Any]:
    base = select(LibraryItem).where(LibraryItem.archived_at.is_(None)).subquery()
    kinds = dict((await db.execute(select(base.c.kind, func.count()).group_by(base.c.kind))).all())
    assets = dict(
        (
            await db.execute(
                select(base.c.asset_kind, func.count())
                .where(base.c.asset_kind.is_not(None))
                .group_by(base.c.asset_kind)
            )
        ).all()
    )
    licenses = dict((await db.execute(select(base.c.license, func.count()).group_by(base.c.license))).all())
    tags: dict[str, int] = defaultdict(int)
    for (raw,) in (
        await db.execute(
            select(LibraryItem.tags).where(LibraryItem.tags.is_not(None), LibraryItem.archived_at.is_(None))
        )
    ).all():
        for t in raw or []:
            tags[str(t)] += 1
    return {
        "kinds": kinds,
        "asset_kinds": assets,
        "licenses": licenses,
        "tags": sorted(tags.items(), key=lambda x: -x[1])[:40],
        "storage": library_files.disk_usage(),
    }


# ── 关联（6.7） ──────────────────────────────────────────────────


async def related(db: AsyncSession, item: LibraryItem, *, limit: int = 12) -> list[dict[str, Any]]:
    """显式关联（提炼、生成、提取、双链、手动、用于项目）+ 推导关联（同一事件、同标签、同作者）。"""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    links = (
        (
            await db.execute(
                select(LibraryLink).where(
                    or_(
                        (LibraryLink.from_type == "item") & (LibraryLink.from_id == item.id),
                        (LibraryLink.to_type == "item") & (LibraryLink.to_id == item.id),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for link in links:
        other = (
            (link.to_type, link.to_id)
            if (link.from_type, link.from_id) == ("item", item.id)
            else (link.from_type, link.from_id)
        )
        if other in seen:
            continue
        seen.add(other)
        out.append({"type": other[0], "id": other[1], "relation": link.relation, "link_id": link.id})
    if item.content_id:
        gid = (
            await db.execute(select(_em.c.event_group_id).where(_em.c.content_id == item.content_id).limit(1))
        ).scalar()
        if gid:
            cids = list((await db.execute(select(_em.c.content_id).where(_em.c.event_group_id == gid))).scalars())
            rows = (
                await db.execute(
                    select(LibraryItem.id).where(
                        LibraryItem.content_id.in_(cids), LibraryItem.id != item.id, LibraryItem.archived_at.is_(None)
                    )
                )
            ).scalars()
            for rid in rows:
                if ("item", rid) not in seen:
                    seen.add(("item", rid))
                    out.append({"type": "item", "id": rid, "relation": LinkRelation.SAME_EVENT.value})
    if item.author:
        rows = (
            await db.execute(
                select(LibraryItem.id)
                .where(LibraryItem.author == item.author, LibraryItem.id != item.id, LibraryItem.archived_at.is_(None))
                .limit(5)
            )
        ).scalars()
        for rid in rows:
            if ("item", rid) not in seen:
                seen.add(("item", rid))
                out.append({"type": "item", "id": rid, "relation": LinkRelation.SAME_AUTHOR.value})
    for tag in (item.tags or [])[:3]:
        rows = (
            await db.execute(
                select(LibraryItem.id)
                .where(json_has(LibraryItem.tags, tag), LibraryItem.id != item.id, LibraryItem.archived_at.is_(None))
                .limit(5)
            )
        ).scalars()
        for rid in rows:
            if ("item", rid) not in seen:
                seen.add(("item", rid))
                out.append({"type": "item", "id": rid, "relation": LinkRelation.SAME_TAG.value})
    return out[: max(limit, 1) * 3]


async def resolve_refs(db: AsyncSession, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """给关联补上标题和缩略图信息。"""
    from app.models.dossier import TopicDossier

    by_type: dict[str, set[int]] = defaultdict(set)
    for r in refs:
        by_type[r["type"]].add(r["id"])
    titles: dict[tuple[str, int], dict[str, Any]] = {}
    if by_type.get("item"):
        for it in (await db.execute(select(LibraryItem).where(LibraryItem.id.in_(by_type["item"])))).scalars():
            titles[("item", it.id)] = {
                "title": it.title,
                "kind": it.kind,
                "asset_kind": it.asset_kind,
                "thumb": bool(it.thumb_small),
                "color": it.dominant_color,
            }
    if by_type.get("note"):
        for n in (await db.execute(select(Note).where(Note.id.in_(by_type["note"])))).scalars():
            titles[("note", n.id)] = {"title": (n.body or "").split("\n")[0][:60] or "随笔", "kind": "note"}
    if by_type.get("content"):
        for c in (await db.execute(select(ContentItem).where(ContentItem.id.in_(by_type["content"])))).scalars():
            titles[("content", c.id)] = {"title": c.title, "kind": c.media_type or "article"}
    if by_type.get("dossier"):
        for d in (await db.execute(select(TopicDossier).where(TopicDossier.id.in_(by_type["dossier"])))).scalars():
            titles[("dossier", d.id)] = {"title": d.title, "kind": "dossier"}
    return [{**r, **titles.get((r["type"], r["id"]), {"title": f"{r['type']} #{r['id']}"})} for r in refs]


async def get_item(db: AsyncSession, item_id: int) -> dict[str, Any]:
    item = await get_item_model(db, item_id)
    rel = await resolve_refs(db, await related(db, item))
    boards = (
        await db.execute(
            select(LibraryBoard.id, LibraryBoard.name)
            .join(LibraryBoardItem, LibraryBoardItem.board_id == LibraryBoard.id)
            .where(LibraryBoardItem.item_id == item.id)
        )
    ).all()
    return {**item_view(item), "related": rel, "boards": [{"id": i, "name": n} for i, n in boards]}


async def link_items(
    db: AsyncSession, a: tuple[str, int], b: tuple[str, int], relation: str = LinkRelation.MANUAL.value
) -> None:
    await ensure_link(db, a, b, relation)
    await db.commit()


async def unlink(db: AsyncSession, link_id: int) -> None:
    link = await db.get(LibraryLink, link_id)
    if link is not None:
        await db.delete(link)
        await db.commit()


# ── 画板 ─────────────────────────────────────────────────────────


async def list_boards(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(LibraryBoard, func.count(LibraryBoardItem.id))
            .outerjoin(LibraryBoardItem, LibraryBoardItem.board_id == LibraryBoard.id)
            .group_by(LibraryBoard.id)
            .order_by(LibraryBoard.updated_at.desc())
        )
    ).all()
    out = []
    for b, n in rows:
        covers = (
            await db.execute(
                select(LibraryItem.id, LibraryItem.dominant_color, LibraryItem.thumb_small)
                .join(LibraryBoardItem, LibraryBoardItem.item_id == LibraryItem.id)
                .where(LibraryBoardItem.board_id == b.id)
                .order_by(LibraryBoardItem.position, LibraryBoardItem.id)
                .limit(4)
            )
        ).all()
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "description": b.description,
                "count": n,
                "covers": [{"id": i, "color": c, "thumb": bool(t)} for i, c, t in covers],
                "updated_at": b.updated_at,
            }
        )
    return out


async def create_board(db: AsyncSession, name: str, description: str | None = None) -> LibraryBoard:
    name = name.strip()
    if not name:
        raise LibraryError("画板名不能为空")
    b = LibraryBoard(name=name[:200], description=description)
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


async def add_to_board(db: AsyncSession, board_id: int, item_ids: list[int]) -> int:
    board = await db.get(LibraryBoard, board_id)
    if board is None:
        raise LibraryNotFoundError("画板不存在")
    have = set(
        (await db.execute(select(LibraryBoardItem.item_id).where(LibraryBoardItem.board_id == board_id))).scalars()
    )
    pos = len(have)
    added = 0
    for iid in item_ids:
        if iid in have:
            continue
        db.add(LibraryBoardItem(board_id=board_id, item_id=iid, position=pos))
        have.add(iid)
        pos += 1
        added += 1
    board.updated_at = datetime.now(UTC)
    await db.commit()
    return added


async def remove_from_board(db: AsyncSession, board_id: int, item_id: int) -> None:
    row = (
        await db.execute(
            select(LibraryBoardItem).where(LibraryBoardItem.board_id == board_id, LibraryBoardItem.item_id == item_id)
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()


async def delete_board(db: AsyncSession, board_id: int) -> None:
    b = await db.get(LibraryBoard, board_id)
    if b is not None:
        await db.delete(b)
        await db.commit()
