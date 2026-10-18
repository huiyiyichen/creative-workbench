"""阶段 1：内容模型补全、免费初筛、分析漏斗与预算、模型调用溯源（改造方案 2.3 / 3.3 / 4.1 / 4.2）。"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, ContentStatus
from app.models.content_observation import ContentJourney
from app.models.llm_model import LlmCallLog
from app.models.source import Source, SourceKind
from app.repositories.content_repo import ContentRepo
from app.services import analysis_funnel as funnel, trace_payloads
from app.services.content_enrichment import (
    attributed_date_for,
    legacy_metrics_record,
    media_type_for,
    metrics_from_entry,
)
from app.services.llm.call_context import current_llm_context, llm_call_context
from app.services.triage import DEFAULT_WEIGHTS, TriageContext, combine, keyword_hits, triage_entry

NOW = datetime(2026, 10, 18, 4, 0, tzinfo=UTC)  # 北京时间 12:00


# ── 内容模型 ──────────────────────────────────────────────


def test_attributed_date_uses_published_then_crawled_in_shanghai():
    # UTC 10-17 20:00 = 北京时间 10-18 04:00
    assert attributed_date_for(datetime(2026, 10, 17, 20, 0, tzinfo=UTC), NOW) == date(2026, 10, 18)
    assert attributed_date_for(None, datetime(2026, 10, 18, 17, 0, tzinfo=UTC)) == date(2026, 10, 19)
    assert attributed_date_for(None, None) is None


def test_media_type_explicit_then_platform():
    assert media_type_for({"media_type": "prompt"}, source_type="RSS", platform="web") == "prompt"
    assert media_type_for({}, source_type="RSSHub", platform="bilibili") == "video"
    assert media_type_for({}, source_type="API", platform="github") == "repo"
    assert media_type_for({}, source_type="Reddit", platform="reddit") == "post"
    assert media_type_for({}, source_type="RSS", platform="web") == "article"


def test_metrics_keep_missing_values_absent():
    entry = {"metrics": {"views": "12,345", "likes": None, "bogus": 3, "stars": True}}
    assert metrics_from_entry(entry) == {"views": 12345.0}
    assert metrics_from_entry({"_zhihu_meta": {"hot_score": "0", "rank": 3}}) == {"rank": 3.0}
    assert metrics_from_entry({}) == {}
    assert legacy_metrics_record({}) is None
    assert legacy_metrics_record({"views": 10.0}) == {
        "views": 10,
        "likes": None,
        "comments": None,
        "shares": None,
        "favorites": None,
    }


def test_twitter_rss_has_no_placeholder_zero_metrics():
    from app.services.content_pipeline import _build_metrics_record

    assert _build_metrics_record({"_twitter_rss_meta": {}}) is None


# ── 免费初筛 ──────────────────────────────────────────────


def test_combine_ignores_missing_signals():
    assert combine({"engagement": None, "freshness": 1.0}, DEFAULT_WEIGHTS) == 100.0
    assert combine({"engagement": None}, DEFAULT_WEIGHTS) is None


def test_keyword_hits_need_every_word():
    assert keyword_hits("Opus 5.5 视频生成实测", ["opus 视频", "sora"]) == ["opus 视频"]


def test_triage_entry_scores_and_explains():
    ctx = TriageContext(source_value={7: 0.8}, keywords=["Opus"], now=NOW)
    score, signals = triage_entry(
        title="Opus 5.5 发布",
        summary=None,
        metrics={"views": 1_000_000, "rank": 1},
        published_at=NOW - timedelta(hours=1),
        source_id=7,
        ctx=ctx,
    )
    assert signals["keyword_hits"] == ["Opus"]
    assert signals["engagement"] == pytest.approx(1.0)
    assert score is not None and score > 90

    low, low_signals = triage_entry(
        title="无关内容", summary=None, metrics={}, published_at=NOW - timedelta(days=5), source_id=None, ctx=ctx
    )
    assert low_signals["keyword"] == 0.0 and low_signals["freshness"] == 0.0
    assert low == 0.0


# ── 调用溯源 ──────────────────────────────────────────────


def test_llm_call_context_nests_and_resets():
    with llm_call_context(content_id=5):
        with llm_call_context(run_id="r1"):
            ctx = current_llm_context()
            assert (ctx.content_id, ctx.run_id) == (5, "r1")
        assert current_llm_context().run_id is None
    assert current_llm_context().content_id is None


def test_trace_payload_is_redacted_and_compressed(tmp_path):
    ref = trace_payloads.save_payload(
        "req1",
        {
            "messages": [{"role": "user", "content": "key sk-abcdefghijklmnop1234 Authorization: Bearer xyz"}],
            "api_key": "secret",
        },
        root=tmp_path,
    )
    assert ref and ref.endswith("req1.json.gz")
    raw = gzip.open(tmp_path / ref).read().decode()
    assert "abcdefghijklmnop" not in raw and "xyz" not in raw and "secret" not in raw
    assert trace_payloads.load_payload(ref, root=tmp_path)["api_key"] == "***"
    assert trace_payloads.load_payload("../../etc/passwd", root=tmp_path) is None


@pytest.mark.asyncio
async def test_record_llm_call_carries_context_and_payload(db, monkeypatch, tmp_path):
    from app.services import llm_usage

    monkeypatch.setattr(trace_payloads, "TRACE_ROOT", tmp_path)
    with llm_call_context(content_id=42, run_id="run-a", step_id="s1"):
        log = await llm_usage.record_llm_call(
            db,
            model=None,
            request_model="m",
            scene="content_analysis",
            status="DONE",
            trace_payload={"messages": [{"role": "user", "content": "分析这条"}], "response": "好的"},
        )
    assert (log.content_id, log.run_id, log.step_id) == (42, "run-a", "s1")
    assert log.prompt_summary == "分析这条" and log.response_summary == "好的"
    assert (tmp_path / log.payload_ref).exists()


# ── 分析漏斗与预算 ─────────────────────────────────────────


def _item(n: int, **kw) -> ContentItem:
    base = {
        "title": f"内容 {n}",
        "url": f"https://example.com/{n}",
        "status": ContentStatus.PENDING,
        "content_hash": f"h{n}",
        "crawled_at": datetime.now(UTC),
    }
    base.update(kw)
    return ContentItem(**base)


@pytest.mark.asyncio
async def test_quick_batch_marks_verdicts_and_journey(db, monkeypatch):
    db.add_all(
        [
            _item(1, triage_score=80),
            _item(2, triage_score=45),
            _item(3, triage_score=10),  # 未过初筛线
            _item(4, triage_score=90, crawled_at=datetime.now(UTC) - timedelta(days=4)),  # 排队超期
        ]
    )
    await db.commit()
    seen: list[list[int]] = []

    async def fake_llm(messages, **kwargs):
        assert kwargs["scene"] == "quick_judge"
        ids = [json.loads(line)["id"] for line in messages[1]["content"].split("\n") if line.startswith("{")]
        seen.append(ids)
        return {"items": [{"id": ids[0], "worth": True, "tags": ["AI"], "summary": "值得"}]}, {}

    monkeypatch.setattr("app.services.llm.provider.call_llm_json_with_metadata", fake_llm)
    stats = await funnel.run_quick_batch(db, funnel.FunnelSettings(triage_threshold=35))
    assert stats == {"judged": 2, "passed": 1, "fallback": 0}
    assert len(seen[0]) == 2  # 按初筛分从高到低，只取过线且未超期的

    rows = {i.title: i for i in (await db.execute(select(ContentItem))).scalars()}
    assert rows["内容 1"].full_eligible is True and rows["内容 1"].quick_result["tags"] == ["AI"]
    # 模型漏判的条目按初筛分兜底：45 < 35 + 15 不放行
    assert rows["内容 2"].full_eligible is False and rows["内容 2"].quick_result["fallback"] is True
    assert rows["内容 3"].full_eligible is None and rows["内容 4"].full_eligible is None
    stages = (await db.execute(select(ContentJourney.stage))).scalars().all()
    assert stages.count("quick") == 2


@pytest.mark.asyncio
async def test_quick_batch_falls_back_when_model_unavailable(db, monkeypatch):
    db.add_all([_item(1, triage_score=70), _item(2, triage_score=40)])
    await db.commit()

    async def broken(*a, **k):
        raise RuntimeError("no model")

    monkeypatch.setattr("app.services.llm.provider.call_llm_json_with_metadata", broken)
    stats = await funnel.run_quick_batch(db, funnel.FunnelSettings(triage_threshold=35))
    assert stats["fallback"] == 1 and stats["passed"] == 1


@pytest.mark.asyncio
async def test_budget_counts_only_today_and_analysis_scenes(db):
    today = datetime.now(UTC)
    db.add_all(
        [
            LlmCallLog(request_id="a", scene="content_analysis", status="DONE", total_cost=3.0, created_at=today),
            LlmCallLog(request_id="b", scene="quick_judge", status="DONE", total_cost=2.5, created_at=today),
            LlmCallLog(request_id="c", scene="report", status="DONE", total_cost=100, created_at=today),
            LlmCallLog(
                request_id="d",
                scene="content_analysis",
                status="DONE",
                total_cost=9,
                created_at=today - timedelta(days=2),
            ),
        ]
    )
    await db.commit()
    status = await funnel.budget_status(db, funnel.FunnelSettings(daily_budget=5))
    assert status["spent"] == pytest.approx(5.5)
    assert await funnel.budget_exhausted(db, funnel.FunnelSettings(daily_budget=5))
    assert not await funnel.budget_exhausted(db, funnel.FunnelSettings(daily_budget=10))


@pytest.mark.asyncio
async def test_prepare_full_queue_stops_on_budget(db, monkeypatch):
    db.add(_item(1, triage_score=None))  # 历史数据：无初筛分直接放行
    db.add(
        LlmCallLog(request_id="x", scene="content_analysis", status="DONE", total_cost=6, created_at=datetime.now(UTC))
    )
    await db.commit()
    result = await funnel.prepare_full_queue(db, funnel.FunnelSettings(daily_budget=5))
    assert result == {"budget_exhausted": True, "released": 1, "judged": 0}


@pytest.mark.asyncio
async def test_funnel_claim_orders_by_triage_and_requires_eligibility(db):
    db.add_all(
        [
            _item(1, triage_score=50, full_eligible=True),
            _item(2, triage_score=90, full_eligible=True),
            _item(3, triage_score=99, full_eligible=False),
            _item(4, triage_score=99, full_eligible=None),
            _item(5, triage_score=95, full_eligible=True, crawled_at=datetime.now(UTC) - timedelta(days=5)),
        ]
    )
    await db.commit()
    repo = ContentRepo(db)
    ids = await repo.claim_pending_analysis_ids(limit=10, funnel=True)
    titles = [(await db.get(ContentItem, i)).title for i in ids]
    assert titles == ["内容 2", "内容 1"]
    # 非漏斗（按需分析 API）不受影响
    assert len(await repo.list_pending_for_analysis(limit=10)) == 3


@pytest.mark.asyncio
async def test_funnel_settings_roundtrip(db):
    cfg = await funnel.save_funnel_settings(db, daily_budget=8, triage_threshold=40)
    assert (cfg.daily_budget, cfg.triage_threshold) == (8.0, 40.0)


@pytest.mark.asyncio
async def test_tracked_keywords_feed_triage_context(db):
    from app.services.triage import load_triage_context

    db.add(Source(name="Opus 5.5", source_type="API", url="kw:opus", kind=SourceKind.KEYWORD.value, query="Opus 5.5"))
    await db.commit()
    ctx = await load_triage_context(db)
    assert ctx.keywords == ["Opus 5.5"]


# ── 入库补全 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_trail_writes_observations_and_journey(db):
    from app.models.content_observation import ContentMetricObservation
    from app.services import content_pipeline as cp

    src = Source(name="B站", source_type="API", url="bili:1", platform="bilibili")
    db.add(src)
    await db.commit()
    entry = {
        "title": "Opus 视频",
        "metrics": {"views": 5000, "likes": 300},
        "platform_item_id": "BV1xx",
        "author_id": "42",
        "media": {"duration": 61, "orientation": "landscape"},
        "published_at": datetime.now(UTC),
    }
    fields = cp._enrichment_fields(
        entry, source=src, source_type="API", triage_ctx=TriageContext(keywords=["opus"], now=datetime.now(UTC))
    )
    assert fields["media_type"] == "video" and fields["platform_item_id"] == "BV1xx"
    assert fields["triage_signals"]["keyword_hits"] == ["opus"]
    item = ContentItem(
        title="Opus 视频",
        url="https://b.example/1",
        source_id=src.id,
        source_name="B站",
        content_hash="hx",
        status=ContentStatus.PENDING,
        skip_analysis=False,
        **fields,
    )
    ids = await cp._persist_new_content_items(db, [item], [None], category_counts={})
    await cp._record_ingest_trail(db, [item], ids, {"hx": {"views": 5000.0, "likes": 300.0}})
    await db.commit()
    obs = (await db.execute(select(ContentMetricObservation.metric))).scalars().all()
    assert sorted(obs) == ["likes", "views"]
    stages = (await db.execute(select(ContentJourney.stage))).scalars().all()
    assert stages == ["collected", "triage"]
    saved = (await db.execute(select(ContentItem))).scalar_one()
    assert saved.attributed_date is not None and saved.analysis_level == "none"


@pytest.mark.asyncio
async def test_report_window_uses_attributed_date(db):
    from app.models.analysis import AiAnalysis

    window_start = datetime(2026, 10, 17, 16, 0)  # 北京时间 10-18 00:00（UTC naive）
    window_end = datetime(2026, 10, 18, 15, 59)
    rows = [
        # 10-18 发布、当天采到 → 进 10-18
        _item(1, attributed_date=date(2026, 10, 18), crawled_at=datetime(2026, 10, 18, 10, 0, tzinfo=UTC)),
        # 昨天发布、今天采到 → 归昨天，不进今天
        _item(2, attributed_date=date(2026, 10, 17), crawled_at=datetime(2026, 10, 18, 1, 0, tzinfo=UTC)),
        # 旧数据没有归属日期 → 按采集时间
        _item(3, attributed_date=None, crawled_at=datetime(2026, 10, 18, 2, 0, tzinfo=UTC)),
        # 10-18 发布、10-20 补采到 → 晚于窗口结束，不改写已生成的日报（进空档回看）
        _item(4, attributed_date=date(2026, 10, 18), crawled_at=datetime(2026, 10, 20, 2, 0, tzinfo=UTC)),
    ]
    db.add_all(rows)
    await db.flush()
    for r in rows:
        db.add(AiAnalysis(content_id=r.id, curation_score=60, risk_score=10, summary="s"))
    await db.commit()
    items = await ContentRepo(db).list_for_report_window(
        window_start=window_start, window_end=window_end, attributed_date=date(2026, 10, 18)
    )
    assert sorted(i.title for i in items) == ["内容 1", "内容 3"]


@pytest.mark.asyncio
async def test_existing_content_gets_throttled_observations(db):
    from app.models.content_observation import ContentMetricObservation
    from app.services import content_pipeline as cp

    db.add(_item(1))
    await db.commit()
    await cp._observe_existing(db, [(1, {"metrics": {"views": 10}})])
    await cp._observe_existing(db, [(1, {"metrics": {"views": 20}})])  # 30 分钟内不重复记
    await cp._observe_existing(db, [(1, {"metrics": {}})])
    await db.commit()
    values = (await db.execute(select(ContentMetricObservation.value))).scalars().all()
    assert values == [10.0]


@pytest.mark.asyncio
async def test_source_recent_includes_series_and_ready_cover(db):
    from app.models.content_observation import ContentMetricObservation, MediaAsset
    from app.services.collection_service import list_source_recent

    src = Source(name="kw", source_type="Keyword", url="keyword://x", kind="keyword")
    db.add(src)
    await db.flush()
    asset = MediaAsset(source_url="u", url_hash="hh", status="ready", dominant_color="#112233", attempts=1)
    db.add(asset)
    await db.flush()
    item = _item(1, source_id=src.id, cover_asset_id=asset.id, media={"duration": 61})
    db.add(item)
    await db.flush()
    t0 = datetime.now(UTC) - timedelta(hours=2)
    db.add_all(
        [
            ContentMetricObservation(content_id=item.id, metric="views", value=10, observed_at=t0),
            ContentMetricObservation(content_id=item.id, metric="views", value=30, observed_at=t0 + timedelta(hours=1)),
        ]
    )
    await db.commit()
    rows = await list_source_recent(db, src.id)
    assert rows[0]["cover_asset_id"] == asset.id and rows[0]["cover_color"] == "#112233"
    assert [p["value"] for p in rows[0]["series"]["views"]] == [10, 30] and rows[0]["latest"] == {"views": 30}
    assert rows[0]["duration"] == 61
