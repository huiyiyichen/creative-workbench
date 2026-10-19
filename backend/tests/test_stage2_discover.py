"""阶段 2：选题结论（4.3）、趋势计算 v2（5.3）、今日 / 条目详情 / 专题接口。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1 import discover
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.analysis import AiAnalysis
from app.models.content import ContentItem, ContentStatus
from app.models.content_event import ContentEventGroup, ContentEventMember
from app.models.content_observation import ContentJourney, ContentMetricObservation
from app.models.dossier import TopicDossier, VerdictMark
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun
from app.models.trend import TopicTrend
from app.services import dossiers, topic_signals, verdict_service
from app.services.auth_service import get_local_user
from app.services.topic_signals import MemberFacts, classify_status, hourly_signal
from app.services.verdict import VerdictFacts, compute_verdict

NOW = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)


# ── 结论（纯规则） ──


def test_verdict_worth_when_several_signals_line_up():
    facts = VerdictFacts(
        title="Opus 5.5 发布",
        platform="bilibili",
        media_type="video",
        published_at=NOW - timedelta(hours=6),
        crawled_at=NOW,
        metrics={"views": 1_200_000},
        event_id=3,
        event_members=4,
        event_platforms=["bilibili", "hn", "github"],
        keyword_hits=["Opus 5.5"],
        related_favorites=4,
        topic_status="rising",
    )
    r = compute_verdict(facts, now=NOW)
    assert r.verdict == "worth"
    assert r.reason.startswith("3 个平台在报同一件事")
    assert "你收藏过 4 条相关内容" in r.reason
    assert r.key_points[0] == "3 平台"
    assert "播放 120万" in r.key_points
    assert "评论未采集" in r.missing
    assert r.detail["points"] >= 3


def test_verdict_rss_without_metrics_and_skip():
    facts = VerdictFacts(
        title="一篇普通博客",
        platform=None,
        media_type="article",
        published_at=NOW - timedelta(days=10),
        crawled_at=NOW,
        is_rss=True,
    )
    r = compute_verdict(facts, now=NOW)
    assert r.verdict == "skip"
    assert r.basis["heat"]["state"] == "无平台指标"
    assert "话题观测不足" in r.missing and "未分析" in r.missing


def test_verdict_risk_rules_and_score():
    base = {"platform": "web", "media_type": "article", "published_at": NOW, "crawled_at": NOW, "keyword_hits": ["x"]}
    assert compute_verdict(VerdictFacts(title="博彩平台推荐", **base), now=NOW).verdict == "skip"
    risky = compute_verdict(VerdictFacts(title="ok", risk_score=80, **base), now=NOW)
    assert risky.verdict == "skip" and "风险分 80" in risky.reason


def test_verdict_stale_caps_at_watch():
    facts = VerdictFacts(
        title="老内容",
        platform="github",
        media_type="repo",
        published_at=NOW - timedelta(days=20),
        crawled_at=NOW,
        metrics={"stars": 9000},
        keyword_hits=["a"],
        related_favorites=2,
        quality=80,
    )
    r = compute_verdict(facts, now=NOW)
    assert r.verdict == "watch"
    assert "已发布 20 天" in r.reason


# ── 趋势（纯计算） ──


def test_hourly_signal_marks_unobserved_hours_none():
    m = MemberFacts(
        1,
        "bilibili",
        1,
        NOW - timedelta(hours=1, minutes=30),
        observations=[
            ("views", NOW - timedelta(hours=2), 100.0),
            ("views", NOW - timedelta(minutes=10), 1100.0),
            ("rank", NOW - timedelta(minutes=10), 1.0),
        ],
    )
    observed = {NOW.replace(minute=0) - timedelta(hours=3)}
    s = hourly_signal([m], observed_hours=observed, end=NOW, hours=4)
    # 小时桶 01:00 / 02:00 / 03:00 / 04:00
    assert s[0] == 0.0  # 有同步、无信号
    assert s[1] == 1.0  # 02:30 发布一条
    assert s[2] == pytest.approx(0.5 * 3.0004 + 1.0, rel=1e-3)  # 03:50 增量 1000 + 排名第 1
    assert s[3] is None  # 没有任何观测


def test_classify_status_variants():
    first = NOW - timedelta(days=5)
    flat = [1.0] * 96
    assert classify_status([1.0] * 48, first_seen=NOW - timedelta(hours=3), now=NOW)[0] == "new"
    rising = [0.0] * 72 + [1.0] * 24
    assert classify_status(rising, first_seen=first, now=NOW)[0] == "rising"
    up = [1.0] * 48 + [2.0] * 24 + [3.2] * 24
    assert classify_status(up, first_seen=first, now=NOW)[0] == "rising"
    cooling = [5.0] * 48 + [3.0] * 24 + [1.0] * 24
    assert classify_status(cooling, first_seen=first, now=NOW)[0] == "cooling"
    peak = [1.0] * 48 + [4.0] * 24 + [3.0] * 24
    assert classify_status(peak, first_seen=first, now=NOW)[0] == "peak"
    status, info = classify_status(flat, first_seen=first, now=NOW)
    assert status == "steady" and info["streak_days"] == 4
    assert classify_status([None] * 96, first_seen=first, now=NOW)[0] == "quiet"


# ── 数据库：趋势 → 结论 → 专题 → 接口 ──


async def _seed(db):
    now = datetime.now(UTC)
    kw = Source(name="Opus 5.5 视频", url="keyword://opus", kind="keyword", query="Opus 5.5", platforms=["bilibili"])
    db.add(kw)
    await db.flush()
    items = []
    for i, (platform, hours) in enumerate([("bilibili", 2), ("hn", 30), ("github", 60), ("bilibili", 80)]):
        c = ContentItem(
            title=f"Opus 5.5 第 {i} 条",
            url=f"https://ex.com/{i}",
            status=ContentStatus.PENDING,
            platform=platform,
            source_id=kw.id,
            media_type="video" if platform == "bilibili" else "article",
            published_at=now - timedelta(hours=hours),
            crawled_at=now - timedelta(hours=hours) + timedelta(minutes=5),
            analysis_level="none",
            comment_state="none",
            triage_signals={"keyword_hits": ["Opus 5.5"]},
        )
        db.add(c)
        items.append(c)
    other = ContentItem(
        title="天气很好",
        url="https://ex.com/w",
        status=ContentStatus.PENDING,
        source_type="rss",
        crawled_at=now,
        analysis_level="none",
        comment_state="none",
    )
    db.add(other)
    await db.flush()
    group = ContentEventGroup(
        canonical_content_id=items[3].id,
        representative_content_id=items[3].id,
        first_occurrence_at=now - timedelta(hours=80),
        last_occurrence_at=now - timedelta(hours=2),
    )
    db.add(group)
    await db.flush()
    for c in items:
        db.add(
            ContentEventMember(
                event_group_id=group.id,
                content_id=c.id,
                relation_type="corroboration",
                confidence=0.9,
                match_method="local_vector",
                review_status="auto",
            )
        )
    db.add(
        ContentMetricObservation(
            content_id=items[0].id, metric="views", value=1000, observed_at=now - timedelta(hours=1)
        )
    )
    db.add(ContentMetricObservation(content_id=items[0].id, metric="views", value=300_000, observed_at=now))
    db.add(
        AiAnalysis(content_id=items[3].id, summary="代表的分析", creator_angles=[{"title": "实测对比"}], risk_score=10)
    )
    for h in range(0, 90, 6):
        db.add(
            SourceSyncRun(
                source_id=kw.id,
                started_at=now - timedelta(hours=h),
                finished_at=now - timedelta(hours=h),
                status="success",
            )
        )
    await db.commit()
    return kw, items, other, group


@pytest.mark.asyncio
async def test_signals_verdicts_dossiers_and_api(db):
    kw, items, other, group = await _seed(db)

    result = await topic_signals.compute_topic_signals(db)
    await db.commit()
    assert result["topics"] == 2
    rows = (await db.execute(select(TopicTrend).where(TopicTrend.calculation_version == "signal-v2"))).scalars().all()
    ev = next(r for r in rows if r.topic_kind == "event")
    assert ev.platform_distribution == {"bilibili": 2, "hn": 1, "github": 1}
    assert ev.first_platform == "bilibili"
    assert len(ev.series) == topic_signals.SERIES_HOURS
    assert ev.status in {"rising", "steady", "peak", "cooling"}
    # 再算一次同一天覆盖，不重复
    await topic_signals.compute_topic_signals(db)
    await db.commit()
    assert len((await db.execute(select(TopicTrend))).scalars().all()) == 2

    counts = await verdict_service.refresh_verdicts(db)
    assert sum(counts.values()) == 5
    await db.refresh(items[0])
    assert items[0].verdict == "worth"
    assert "3 个平台在报同一件事" in items[0].verdict_data["reason"]
    journey = (await db.execute(select(ContentJourney).where(ContentJourney.stage == "verdict"))).scalars().all()
    assert len(journey) == 5

    sync = await dossiers.sync_dossiers(db)
    assert sync["created"] >= 1  # 追踪词专题；事件 streak 不足 3 天时不自动建
    ds = (await db.execute(select(TopicDossier))).scalars().all()
    assert any(d.watch_source_id == kw.id for d in ds)

    user = await get_local_user(db)
    await db.commit()
    app = FastAPI()
    app.include_router(discover.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        feed = (await client.get("/today/feed")).json()
        assert feed["total"] >= 2
        assert feed["items"][0]["verdict"] == "worth"
        rss = next(i for i in feed["items"] if i["id"] == other.id)
        assert rss["metric"]["state"] == "RSS 无平台指标"

        picks = (await client.get("/today/feed", params={"view": "picks"})).json()
        assert all(i["verdict"] == "worth" for i in picks["items"]) and picks["days"]

        assert (await client.get("/today/signals")).json()["tracks"]
        side = (await client.get("/today/side")).json()
        assert side["watch_terms"][0]["term"] == "Opus 5.5"
        assert side["resonance"]["rows"][0]["event_id"] == group.id
        first = (await client.post("/today/seen")).json()
        assert first["away_days"] is None

        # 详情：非代表成员继承代表的分析
        detail = (await client.get(f"/items/{items[0].id}")).json()
        assert detail["analysis"]["inherited_from"] == items[3].id
        assert detail["analysis"]["angles"][0]["title"] == "实测对比"
        assert detail["event"]["others"] and detail["series"]["views"][-1]["value"] == 300_000
        assert detail["verdict_full"]["detail"]["formula"]

        # 不对 → 人工结论优先，计算结论保留
        r = (await client.put(f"/items/{items[0].id}/verdict", json={"verdict": "skip", "note": "旧闻"})).json()
        assert r["verdict"] == "skip" and r["computed"] == "worth"
        mark = (await db.execute(select(VerdictMark))).scalar_one()
        assert mark.computed_verdict == "worth"
        agree = (await client.get("/verdicts/agreement")).json()
        assert agree["corrected"] == 1 and agree["mark_agreement"] == 0.0
        r = (await client.put(f"/items/{items[0].id}/verdict", json={"verdict": None})).json()
        assert r["verdict"] == "worth"

        fb = (await client.put(f"/items/{items[1].id}/feedback", json={"kind": "not_interested"})).json()
        assert fb["feedback"] == "not_interested"

        # 移出此事件：代表被移出时改选
        left = (await client.post(f"/items/{items[3].id}/leave-event")).json()
        assert left["removed"] is True
        await db.refresh(group)
        assert group.representative_content_id != items[3].id

        rising = (await client.get("/hot/rising")).json()
        assert rising["items"] and rising["items"][0]["representative"]
        terms = (await client.get("/hot/watch-terms")).json()["items"]
        assert terms[0]["trend"]["kind"] == "watch_term"

        followed = (await client.post("/dossiers/follow", json={"event_id": group.id})).json()
        d = (await client.get(f"/dossiers/{followed['id']}")).json()
        assert d["followed"] is True and d["timeline"]
        assert d["first_by_platform"][0]["platform"] == "github"  # 最早的 B站条目已移出事件
        listed = (await client.get("/dossiers")).json()["items"]
        assert {x["id"] for x in listed} >= {followed["id"]}
        assert (await client.get("/items/999999")).status_code == 404
