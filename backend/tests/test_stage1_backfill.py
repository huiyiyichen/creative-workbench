"""阶段 1：空档补采（改造方案 3.7）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun, SyncRunStatus
from app.services import gap_backfill
from app.services.backfill_context import BackfillWindow, backfill_window, current_backfill
from app.services.scrapers.platform import PlatformScraper

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _run(source_id: int, finished: datetime) -> SourceSyncRun:
    return SourceSyncRun(
        source_id=source_id,
        trigger="schedule",
        started_at=finished,
        finished_at=finished,
        status=SyncRunStatus.SUCCESS.value,
    )


@pytest.mark.asyncio
async def test_find_gaps_and_backfill_marks_lists_missing(db, test_session_factory):
    db.add_all(
        [
            Source(id=1, name="UP", source_type="Platform", url="platform://bilibili/user/1", enabled=True,
                   fetch_interval_minutes=180, kind="subscription"),
            Source(id=2, name="热榜", source_type="DouyinHot", url="https://www.douyin.com/hot", enabled=True,
                   fetch_interval_minutes=30, kind="list"),
            Source(id=3, name="刚同步", source_type="RSS", url="https://a.example/feed", enabled=True,
                   fetch_interval_minutes=60),
        ]
    )  # fmt: skip
    db.add_all([_run(1, NOW - timedelta(days=10)), _run(2, NOW - timedelta(hours=5)), _run(3, NOW - timedelta(minutes=30))])
    await db.commit()

    gaps = await gap_backfill.find_gaps(db, now=NOW)
    assert {(g.source_id, g.is_list) for g in gaps} == {(1, False), (2, True)}

    seen = []

    async def fake_sync(session, source_id, **kwargs):
        seen.append((source_id, kwargs, current_backfill()))
        return SimpleNamespace(run=object(), failed=False)

    @asynccontextmanager
    async def factory():
        async with test_session_factory() as s:
            yield s

    stats = await gap_backfill.run_gap_backfill(factory, sync=fake_sync, now=NOW)
    assert stats == {"gaps": 2, "lists_missing": 1, "backfilled": 1, "failed": 0}
    source_id, kwargs, window = seen[0]
    assert source_id == 1 and kwargs["is_backfill"] is True
    assert window.since == NOW - timedelta(days=7)  # 最多补 7 天

    async with test_session_factory() as s:
        missing = (await s.execute(select(SourceSyncRun).where(SourceSyncRun.source_id == 2,
                                                               SourceSyncRun.is_backfill.is_(True)))).scalar_one()  # fmt: skip
    assert missing.status == SyncRunStatus.SKIPPED.value and "无法补回" in missing.error_message


@pytest.mark.asyncio
async def test_platform_scraper_pages_back_until_since():
    pages = {
        "1": [{"bvid": f"BV{i}", "title": f"t{i}", "pubdate": int((NOW - timedelta(hours=i)).timestamp())} for i in range(30)],
        "2": [{"bvid": f"BV{i}", "title": f"t{i}", "pubdate": int((NOW - timedelta(hours=i)).timestamp())} for i in range(30, 60)],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "finger/spi" in url or url.startswith("https://www.bilibili.com/"):
            return httpx.Response(200, json={"code": 0, "data": {"b_3": "x"}})
        if "/nav" in url:
            return httpx.Response(200, json={"code": 0, "data": {"wbi_img": {"img_url": "https://a/7cd084941338484aae1ad9425b84077c.png", "sub_url": "https://a/4932caff0ff746eab6f01bf08b70ac45.png"}}})
        if "arc/search" in url:
            pn = request.url.params.get("pn")
            return httpx.Response(200, json={"code": 0, "data": {"list": {"vlist": pages.get(pn, [])}}})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with backfill_window(BackfillWindow(since=NOW - timedelta(hours=40))):
            entries = await PlatformScraper("platform://bilibili/user/1").fetch(client)
        assert len(entries) == 41  # 0..40 小时前（含边界）
        plain = await PlatformScraper("platform://bilibili/user/1").fetch(client)
        assert len(plain) == 20  # 非补采只取第一页
