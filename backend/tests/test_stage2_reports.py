"""阶段 2：报告的空档回看、时间段、完整度、归档日历、搜索与前后连贯（5.4）。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1 import reports
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.content import ContentItem, ContentStatus
from app.models.daily_report import DailyReport
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun
from app.services import period_reports
from app.services.period_reports import continuity, find_gaps

TZ = ZoneInfo("Asia/Shanghai")


def test_find_gaps_and_continuity():
    d = date(2026, 10, 1)
    collected = {d, d + timedelta(days=1), d + timedelta(days=5), d + timedelta(days=6)}
    assert find_gaps(collected, d, d + timedelta(days=8)) == [
        (d + timedelta(days=2), d + timedelta(days=4)),
        (d + timedelta(days=7), d + timedelta(days=8)),
    ]
    # 单天缺失不算空档
    assert find_gaps({d, d + timedelta(days=2)}, d, d + timedelta(days=2)) == []
    c = continuity(["Opus", "Sora", "MCP"], ["Opus", "Gemini"])
    assert c == {"continued": ["Opus"], "new": ["Gemini"], "dropped": ["Sora", "MCP"]}


def _at(d: date, hour: int = 12) -> datetime:
    return datetime.combine(d, time(hour), tzinfo=TZ).astimezone(UTC)


@pytest.mark.asyncio
async def test_gap_review_calendar_search(db):
    today = date(2026, 10, 19)
    src = Source(name="HN", url="https://hn.example/rss")
    db.add(src)
    await db.flush()
    # 10-10 ~ 10-13 有采集，10-14 ~ 10-17 停了 4 天，10-18 恢复
    for d in [date(2026, 10, 10) + timedelta(days=i) for i in range(4)] + [date(2026, 10, 18)]:
        db.add(SourceSyncRun(source_id=src.id, started_at=_at(d), finished_at=_at(d), status="success"))
    db.add(
        SourceSyncRun(
            source_id=src.id, started_at=_at(date(2026, 10, 12)), finished_at=_at(date(2026, 10, 12)), status="failed"
        )
    )
    for i, d in enumerate([date(2026, 10, 12), date(2026, 10, 15), date(2026, 10, 16)]):
        db.add(
            ContentItem(
                title=f"Opus 5.5 新闻 {i}",
                url=f"https://ex.com/{i}",
                status=ContentStatus.PENDING,
                platform="hn",
                published_at=_at(d),
                crawled_at=_at(date(2026, 10, 18)),
                attributed_date=d,
                analysis_level="none",
                comment_state="none",
                verdict="worth",
                verdict_data={"reason": "3 个平台在报同一件事", "key_points": ["3 平台"]},
            )
        )
    db.add(
        DailyReport(
            report_date="2026-10-12",
            weekday="周一",
            edition="final",
            status="DONE",
            overview="今天 Opus 5.5 发布，多个平台跟进。",
            keywords=json.dumps(["Opus", "MCP"]),
            top_picks=json.dumps([{"title": "Opus 5.5 实测"}]),
        )
    )
    db.add(
        DailyReport(
            report_date="2026-10-13",
            weekday="周二",
            edition="final",
            status="DONE",
            overview="继续发酵",
            keywords=json.dumps([{"word": "Opus"}, {"word": "Gemini"}]),
        )
    )
    await db.commit()

    assert await period_reports.has_collected_data(db, date(2026, 10, 12))
    assert await period_reports.has_collected_data(db, date(2026, 10, 15))  # 有归属到当天的内容（补采得到）
    assert not await period_reports.has_collected_data(db, date(2026, 10, 14))

    gap = await period_reports.detect_and_generate_gap(db, today=today)
    assert gap is not None and (gap.start_date, gap.end_date) == ("2026-10-14", "2026-10-17")
    assert gap.title.startswith("空档回看")
    sec = gap.sections
    assert sec["overview"]["items"] == 2 and sec["overview"]["collected_days"] == 0
    assert {m["title"] for m in sec["missed_worth"]} == {"Opus 5.5 新闻 1", "Opus 5.5 新闻 2"}
    assert gap.completeness["uncollected_days"] == ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17"]
    assert len(gap.completeness["trending_missing_days"]) == 4  # 热榜缺失注明
    # 已生成过就不重复
    assert await period_reports.detect_and_generate_gap(db, today=today) is None

    app = FastAPI()
    app.include_router(reports.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        cal = (await client.get("/reports/calendar", params={"year": 2026, "month": 10})).json()
        by = {d["date"]: d for d in cal["days"]}
        assert by["2026-10-12"]["state"] == "report" and by["2026-10-12"]["headline"] == "Opus 5.5 实测"
        assert by["2026-10-14"]["state"] == "uncollected"
        assert by["2026-10-15"]["state"] == "collected"
        assert cal["gaps"][0]["start_date"] == "2026-10-14"

        found = (await client.get("/reports/search", params={"q": "Opus"})).json()["items"]
        assert {f["kind"] for f in found} >= {"daily"}

        r = (await client.post("/reports/periods", json={"start_date": "2026-10-10", "end_date": "2026-10-18"})).json()
        assert r["kind"] == "range" and r["version"] == 1
        again = (await client.post(f"/reports/periods/{r['id']}/regenerate")).json()
        assert again["version"] == 2
        detail = (await client.get(f"/reports/periods/{again['id']}")).json()
        assert [v["version"] for v in detail["versions"]] == [2, 1]
        assert detail["completeness"]["failed_sources"] == []  # 同一信源当天有成功，不算失败
        bad = await client.post("/reports/periods", json={"start_date": "2026-10-18", "end_date": "2026-10-10"})
        assert bad.status_code == 422

        cont = (await client.get("/reports/daily/2026-10-13/continuity")).json()
        assert cont == {"previous_date": "2026-10-12", "continued": ["Opus"], "new": ["Gemini"], "dropped": ["MCP"]}


@pytest.mark.asyncio
async def test_collection_insights(db):
    from app.models.content_event import ContentEventGroup, ContentEventMember
    from app.services import collection_insights

    now = datetime.now(UTC)
    hot = Source(name="B站热门", url="https://bili/hot", kind="list", platform="bilibili")
    rss = Source(name="arXiv cs.AI", url="https://arxiv/rss", kind="subscription")
    db.add_all([hot, rss])
    await db.flush()
    a = ContentItem(
        title="Opus 5.5 热门",
        url="https://b/1",
        status=ContentStatus.PENDING,
        source_id=hot.id,
        platform="bilibili",
        crawled_at=now,
        analysis_level="none",
        comment_state="none",
    )
    b = ContentItem(
        title="Opus 5.5 讲解",
        url="https://b/2",
        status=ContentStatus.PENDING,
        source_id=hot.id,
        platform="bilibili",
        crawled_at=now,
        analysis_level="none",
        comment_state="none",
    )
    db.add_all([a, b])
    for i in range(201):
        db.add(
            ContentItem(
                title=f"paper {i}",
                url=f"https://arxiv/{i}",
                status=ContentStatus.PENDING,
                source_id=rss.id,
                crawled_at=now - timedelta(hours=1),
                published_at=now - timedelta(hours=3),
                analysis_level="none",
                comment_state="none",
                media_type="article",
            )
        )
    for i in range(3):
        db.add(
            ContentItem(
                title=f"fav {i}",
                url=f"https://v/{i}",
                status=ContentStatus.PENDING,
                platform="bilibili",
                author="像素与噪点",
                author_url="https://space.bilibili.com/42",
                is_favorited=True,
                media_type="video",
                crawled_at=now,
                analysis_level="none",
                comment_state="none",
            )
        )
    await db.flush()
    g = ContentEventGroup(
        canonical_content_id=a.id,
        representative_content_id=a.id,
        first_occurrence_at=now - timedelta(hours=2),
        last_occurrence_at=now,
    )
    db.add(g)
    await db.flush()
    for c in (a, b):
        db.add(
            ContentEventMember(
                event_group_id=g.id,
                content_id=c.id,
                relation_type="corroboration",
                confidence=0.9,
                match_method="local_vector",
                review_status="auto",
            )
        )
    await db.commit()

    out = await collection_insights.build_insights(db)
    assert out["coverage"][0]["event_id"] == g.id
    assert "B站热榜都有，你的订阅 0 条" in out["coverage"][0]["text"]
    kinds = {s["kind"] for s in out["suggestions"]}
    assert {"disable", "subscribe"} <= kinds
    arxiv = next(r for r in out["completeness"] if r["source_id"] == rss.id)
    assert arxiv["published_at"] == 1.0 and arxiv["cover"] == 0.0 and arxiv["delay_hours_median"] == 2.0
    hot_value = next(r for r in out["value"]["sources"] if r["source_id"] == hot.id)
    assert hot_value["duplicate_rate"] == 0.5 and hot_value["first_reports"] == 1
    assert len(out["value"]["favorite_trend"]) == 8
    assert out["structure"]["media_type"][0]["key"] == "article"
