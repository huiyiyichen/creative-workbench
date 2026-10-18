"""封面本地缓存（改造方案 3.4）。

* 只请求平台图片 CDN 白名单域名（文章封面允许与原文同域）；限 5MB、校验 ``image/*``、超时 10 秒；失败 3 次标记失败。
* 转 WebP：最长边 960px（full）+ 320px（thumb），算主色给前端占位。
* 存 ``data/media/covers/<hash 前两位>/<hash>.webp``；超过上限（默认 2GB）按最后访问时间清理，
  已收藏内容引用的与 ``pinned`` 的封面永久保留。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_observation import MediaAsset, MediaAssetStatus
from app.repositories.media_asset_repo import MediaAssetRepository

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(__file__).resolve().parents[2] / "data" / "media" / "covers"
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 10.0
MAX_ATTEMPTS = 3
FULL_EDGE = 960
THUMB_EDGE = 320
CACHE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024

# 平台图片 CDN（后缀匹配）
CDN_ALLOWLIST = (
    "hdslb.com",  # B站
    "biliimg.com",
    "ytimg.com",  # YouTube
    "ggpht.com",
    "githubassets.com",  # GitHub 社交预览
    "githubusercontent.com",
    "redd.it",  # Reddit
    "redditmedia.com",
    "redditstatic.com",
    "douyinpic.com",  # 抖音
    "byteimg.com",
    "xhscdn.com",  # 小红书
    "zhimg.com",  # 知乎
    "sinaimg.cn",
    "qpic.cn",  # 公众号
    "substackcdn.com",
    "medium.com",
)
_REFERERS = {"hdslb.com": "https://www.bilibili.com/", "douyinpic.com": "https://www.douyin.com/"}


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def allowed_cover_url(url: str, *, page_url: str | None = None) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if any(host == d or host.endswith("." + d) for d in CDN_ALLOWLIST):
        return True
    if page_url:  # 文章 og:image 与原文同站（含子域）
        page_host = (urlparse(page_url).hostname or "").lower().removeprefix("www.")
        if page_host and (
            host == page_host or host.endswith("." + page_host) or page_host.endswith("." + host.removeprefix("www."))
        ):
            return True
    return False


def _referer(host: str) -> str | None:
    for suffix, ref in _REFERERS.items():
        if host.endswith(suffix):
            return ref
    return None


def process_image(data: bytes) -> tuple[bytes, bytes, int, int, str]:
    """→ (full_webp, thumb_webp, width, height, 主色 #rrggbb)。CPU 操作，放线程里跑。"""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        width, height = img.size

        def _encode(edge: int) -> bytes:
            copy = img.copy()
            copy.thumbnail((edge, edge))
            buf = io.BytesIO()
            copy.save(buf, format="WEBP", quality=82, method=4)
            return buf.getvalue()

        full = _encode(FULL_EDGE)
        thumb = _encode(THUMB_EDGE)
        r, g, b = img.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))[:3]
    return full, thumb, width, height, f"#{r:02x}{g:02x}{b:02x}"


async def download_image(client: httpx.AsyncClient, url: str) -> bytes:
    host = (urlparse(url).hostname or "").lower()
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if ref := _referer(host):
        headers["Referer"] = ref
    async with client.stream("GET", url, headers=headers, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            raise ValueError(f"不是图片：{ctype or '未知类型'}")
        declared = int(resp.headers.get("content-length") or 0)
        if declared > MAX_BYTES:
            raise ValueError("图片超过 5MB")
        chunks: list[bytes] = []
        total = 0
        async for chunk in resp.aiter_bytes():
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("图片超过 5MB")
            chunks.append(chunk)
    return b"".join(chunks)


def asset_paths(digest: str, root: Path | None = None) -> tuple[Path, Path]:
    base = (root or MEDIA_ROOT) / digest[:2]
    return base / f"{digest}.webp", base / f"{digest}.thumb.webp"


async def cache_cover(
    db: AsyncSession, client: httpx.AsyncClient, url: str, *, page_url: str | None = None, root: Path | None = None
) -> MediaAsset | None:
    """下载并缓存一张封面；已缓存直接返回。不在白名单返回 None。"""
    if not allowed_cover_url(url, page_url=page_url):
        return None
    repo = MediaAssetRepository(db)
    digest = url_hash(url)
    asset = await repo.by_hash(digest)
    if asset is None:
        asset = MediaAsset(source_url=url[:2048], url_hash=digest, status=MediaAssetStatus.PENDING.value, attempts=0)
        db.add(asset)
        await db.flush()
    if asset.status == MediaAssetStatus.READY.value or (
        asset.status == MediaAssetStatus.FAILED.value and asset.attempts >= MAX_ATTEMPTS
    ):
        return asset
    asset.attempts = (asset.attempts or 0) + 1
    try:
        data = await download_image(client, url)
        full, thumb, width, height, color = await asyncio.to_thread(process_image, data)
        full_path, thumb_path = asset_paths(digest, root)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(full)
        thumb_path.write_bytes(thumb)
        base = root or MEDIA_ROOT
        asset.local_path = full_path.relative_to(base).as_posix()
        asset.thumb_path = thumb_path.relative_to(base).as_posix()
        asset.sha256 = hashlib.sha256(data).hexdigest()
        asset.width, asset.height, asset.dominant_color = width, height, color
        asset.bytes = len(full) + len(thumb)
        asset.status = MediaAssetStatus.READY.value
        asset.error = None
    except Exception as exc:
        asset.error = str(exc)[:300]
        asset.status = (
            MediaAssetStatus.FAILED.value if asset.attempts >= MAX_ATTEMPTS else MediaAssetStatus.PENDING.value
        )
        logger.info("cover cache failed (%s/%s) %s: %s", asset.attempts, MAX_ATTEMPTS, url, exc)
    return asset


async def cache_pending_covers(db: AsyncSession, *, limit: int = 40, days: int = 7) -> dict[str, int]:
    """定时任务：给最近采集、还没缓存封面的内容下载封面。"""
    repo = MediaAssetRepository(db)
    items: list[ContentItem] = list(
        await repo.contents_without_asset(limit=limit, since=datetime.now(UTC) - timedelta(days=days))
    )
    stats = {"checked": len(items), "ready": 0, "failed": 0, "skipped": 0}
    if not items:
        return stats
    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT) as client:
        for item in items:
            asset = await cache_cover(db, client, item.cover_url or "", page_url=item.url)
            if asset is None:
                stats["skipped"] += 1
                continue
            if asset.status == MediaAssetStatus.READY.value:
                item.cover_asset_id = asset.id
                stats["ready"] += 1
            elif asset.status == MediaAssetStatus.FAILED.value:
                stats["failed"] += 1
            await db.commit()
    return stats


async def evict_over_limit(db: AsyncSession, *, limit_bytes: int = CACHE_LIMIT_BYTES, root: Path | None = None) -> int:
    repo = MediaAssetRepository(db)
    total = await repo.total_bytes()
    removed = 0
    while total > limit_bytes:
        batch = list(await repo.eviction_candidates())
        if not batch:
            break
        for asset in batch:
            if total <= limit_bytes:
                break
            for rel in (asset.local_path, asset.thumb_path):
                if rel:
                    (root or MEDIA_ROOT).joinpath(rel).unlink(missing_ok=True)
            total -= int(asset.bytes or 0)
            await repo.detach(asset.id)
            await db.delete(asset)
            removed += 1
        await db.commit()
    return removed


def resolve_asset_file(asset: MediaAsset, size: str, root: Path | None = None) -> Path | None:
    rel = asset.thumb_path if size == "thumb" else asset.local_path
    if not rel:
        return None
    base = (root or MEDIA_ROOT).resolve()
    path = (base / rel).resolve()
    if base not in path.parents or not path.exists():
        return None
    return path
