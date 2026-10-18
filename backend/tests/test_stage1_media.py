"""阶段 1：封面本地缓存（改造方案 3.4）。"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.models.content import ContentItem, ContentStatus
from app.models.content_observation import MediaAsset, MediaAssetStatus
from app.services import media_cache


def _png(w=1600, h=900, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_allowlist_and_same_site():
    assert media_cache.allowed_cover_url("https://i0.hdslb.com/bfs/a.jpg")
    assert media_cache.allowed_cover_url("https://i.ytimg.com/vi/x/hqdefault.jpg")
    assert not media_cache.allowed_cover_url("https://evil.example/a.jpg")
    assert media_cache.allowed_cover_url("https://cdn.blog.example/a.jpg", page_url="https://blog.example/post")
    assert not media_cache.allowed_cover_url("ftp://i0.hdslb.com/a.jpg")


def test_process_image_resizes_and_picks_color():
    full, thumb, w, h, color = media_cache.process_image(_png())
    assert (w, h) == (1600, 900) and color == "#c81e1e"
    assert Image.open(io.BytesIO(full)).size == (960, 540)
    assert max(Image.open(io.BytesIO(thumb)).size) == 320
    assert Image.open(io.BytesIO(full)).format == "WEBP"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_cache_cover_downloads_once_with_referer(db, tmp_path):
    calls = []

    def handler(request):
        calls.append(request.headers.get("referer"))
        return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})

    async with _client(handler) as client:
        asset = await media_cache.cache_cover(db, client, "https://i0.hdslb.com/a.png", root=tmp_path)
        again = await media_cache.cache_cover(db, client, "https://i0.hdslb.com/a.png", root=tmp_path)
    assert asset.status == MediaAssetStatus.READY.value and again.id == asset.id
    assert calls == ["https://www.bilibili.com/"]
    assert media_cache.resolve_asset_file(asset, "thumb", root=tmp_path).exists()
    assert media_cache.resolve_asset_file(asset, "full", root=tmp_path).exists()


@pytest.mark.asyncio
async def test_cache_cover_rejects_non_image_and_gives_up_after_three(db, tmp_path):
    async with _client(lambda r: httpx.Response(200, text="<html>", headers={"content-type": "text/html"})) as client:
        for _ in range(4):
            asset = await media_cache.cache_cover(db, client, "https://i0.hdslb.com/b.png", root=tmp_path)
    assert asset.status == MediaAssetStatus.FAILED.value and asset.attempts == 3
    assert "不是图片" in asset.error


@pytest.mark.asyncio
async def test_cache_cover_skips_disallowed_host(db, tmp_path):
    async with _client(lambda r: httpx.Response(500)) as client:
        assert await media_cache.cache_cover(db, client, "https://evil.example/a.png", root=tmp_path) is None


@pytest.mark.asyncio
async def test_evict_keeps_favorited_and_pinned(db, tmp_path):
    now = datetime.now(UTC)
    assets = [
        MediaAsset(source_url=f"u{i}", url_hash=f"h{i}", status="ready", bytes=100, attempts=1,
                   last_accessed_at=now - timedelta(days=10 - i), pinned=(i == 1))
        for i in range(4)
    ]  # fmt: skip
    db.add_all(assets)
    await db.flush()
    db.add(ContentItem(title="t", url="https://x", status=ContentStatus.PENDING, is_favorited=True,
                       cover_asset_id=assets[0].id, content_hash="c"))  # fmt: skip
    await db.commit()
    removed = await media_cache.evict_over_limit(db, limit_bytes=200, root=tmp_path)
    remaining = {a.url_hash for a in (await db.execute(select(MediaAsset))).scalars()}
    assert removed == 2 and remaining == {"h0", "h1"}
