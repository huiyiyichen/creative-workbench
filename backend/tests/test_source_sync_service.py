"""同步记录与自动处理（改造方案 3.3 / 3.9）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.auto_action import AutoAction, AutoActionType
from app.models.source import Source, SourceStatus
from app.models.source_sync_run import SourceSyncRun, SyncErrorKind, SyncRunStatus, SyncTrigger
from app.services import source_sync_service as svc
from app.services.source_sync_service import (
    classify_sync_error,
    paused_retry_due,
    run_source_sync,
    undo_auto_action,
    usual_interval,
)


@pytest.fixture(autouse=True)
def _no_notifications(monkeypatch):
    sent: list = []

    async def fake_notify(actions):
        sent.extend(actions)

    monkeypatch.setattr(svc, "notify_auto_actions", fake_notify)
    return sent


def _source(**kw) -> Source:
    base = {"name": "测试源", "source_type": "RSS", "url": "https://example.com/feed.xml", "enabled": True, "platform": "web"}
    base.update(kw)
    return Source(**base)


def _ok(new: int = 2, fetched: int = 3):
    async def ingest(source, db):
        source.status = SourceStatus.ACTIVE
        source.sync_error = None
        return {"fetched": fetched, "new": new, "duplicates": fetched - new, "skipped": {"short_text": 1}}

    return ingest


def _fail(message: str):
    async def ingest(source, db):
        source.status = SourceStatus.ERROR
        source.sync_error = message
        return {"fetched": 0, "new": 0, "duplicates": 0}

    return ingest


@pytest.mark.parametrize(
    ("message", "kind", "status"),
    [
        ("Client error '429 Too Many Requests' for url 'https://x'", SyncErrorKind.RATE_LIMIT, 429),
        ("Source sync timed out after 450s", SyncErrorKind.TIMEOUT, None),
        ("页面出现验证码，需要手动处理", SyncErrorKind.CAPTCHA, None),
        ("登录态已失效", SyncErrorKind.LOGIN, None),
        ("Client error '403 Forbidden' for url", SyncErrorKind.BLOCKED, 403),
        ("Client error '404 Not Found' for url", SyncErrorKind.API_CHANGED, 404),
        ("something odd", SyncErrorKind.OTHER, None),
    ],
)
def test_classify_sync_error(message, kind, status):
    assert classify_sync_error(message) == (kind, status)


@pytest.mark.asyncio
async def test_success_run_is_recorded(db):
    db.add(_source(id=1))
    await db.commit()

    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_ok())

    run = outcome.run
    assert run is not None
    assert run.status == SyncRunStatus.SUCCESS.value
    assert (run.fetched, run.new, run.duplicates) == (3, 2, 1)
    assert run.skipped == {"short_text": 1}
    assert run.finished_at is not None and run.duration_ms is not None
    assert run.trigger == SyncTrigger.SCHEDULE.value


@pytest.mark.asyncio
async def test_empty_run_is_distinct_from_success(db):
    db.add(_source(id=1))
    await db.commit()
    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_ok(new=0, fetched=0))
    assert outcome.run.status == SyncRunStatus.EMPTY.value


@pytest.mark.asyncio
async def test_crash_inside_ingest_still_records_failed_run(db):
    db.add(_source(id=1))
    await db.commit()

    async def boom(source, db):
        raise RuntimeError("Client error '500 Internal Server Error'")

    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=boom)
    assert outcome.run.status == SyncRunStatus.FAILED.value
    assert outcome.run.http_status == 500
    assert outcome.source.status == SourceStatus.ERROR


@pytest.mark.asyncio
async def test_three_failures_pause_source_and_undo_restores(db, _no_notifications):
    db.add(_source(id=1))
    await db.commit()

    for _ in range(3):
        # 让租约立即可再认领
        src = await db.get(Source, 1)
        src.status = SourceStatus.ERROR
        await db.commit()
        outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_fail("connection reset"))

    source = outcome.source
    assert source.consecutive_failures == 3
    assert source.auto_paused_at is not None
    actions = (await db.execute(select(AutoAction))).scalars().all()
    assert [a.action_type for a in actions] == [AutoActionType.PAUSE_SOURCE.value]
    assert _no_notifications and _no_notifications[-1].action_type == AutoActionType.PAUSE_SOURCE.value

    # 暂停期间的定时同步被跳过，不产生记录
    skipped = await run_source_sync(db, 1, lease_seconds=60, ingest=_ok())
    assert skipped.run is None and skipped.skipped_reason == "auto_paused"

    await undo_auto_action(db, actions[0].id)
    await db.commit()
    await db.refresh(source)
    assert source.auto_paused_at is None
    assert source.consecutive_failures == 0
    assert actions[0].undone_at is not None


@pytest.mark.asyncio
async def test_paused_source_retries_after_six_hours_and_auto_resumes(db):
    long_ago = datetime.now(UTC) - timedelta(hours=7)
    db.add(
        _source(
            id=1,
            auto_paused_at=long_ago,
            auto_pause_reason="连续失败 3 次",
            consecutive_failures=3,
            last_sync_at=long_ago,
        )
    )
    await db.commit()

    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_ok())

    assert outcome.run.trigger == SyncTrigger.RETRY.value
    assert outcome.source.auto_paused_at is None
    assert [a.action_type for a in outcome.actions] == [AutoActionType.RESUME_SOURCE.value]


def test_paused_retry_due_window():
    now = datetime.now(UTC)
    s = _source(auto_paused_at=now - timedelta(hours=2), last_sync_at=now - timedelta(hours=1))
    assert not paused_retry_due(s, now)
    s.last_sync_at = now - timedelta(hours=6, minutes=1)
    s.auto_paused_at = now - timedelta(hours=7)
    assert paused_retry_due(s, now)


@pytest.mark.asyncio
async def test_rate_limit_doubles_interval_then_steps_back(db):
    db.add(_source(id=1, fetch_interval_minutes=60))
    await db.commit()

    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_fail("Client error '429 Too Many Requests'"))
    assert outcome.source.fetch_interval_minutes == 120
    assert outcome.source.base_interval_minutes == 60
    assert AutoActionType.BACKOFF_SOURCE.value in [a.action_type for a in outcome.actions]

    src = await db.get(Source, 1)
    src.status = SourceStatus.ERROR
    await db.commit()
    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_ok())
    assert outcome.source.fetch_interval_minutes == 60
    assert outcome.source.base_interval_minutes is None


@pytest.mark.asyncio
async def test_login_failure_pauses_whole_platform(db):
    db.add_all(
        [
            _source(id=1, name="抖音 A", platform="douyin"),
            _source(id=2, name="抖音 B", platform="douyin", url="https://example.com/b"),
            _source(id=3, name="博客", platform="web", url="https://example.com/c"),
        ]
    )
    await db.commit()

    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_fail("登录态已失效，请重新登录"))

    assert AutoActionType.PAUSE_PLATFORM.value in [a.action_type for a in outcome.actions]
    paused = {s.id for s in (await db.execute(select(Source))).scalars() if s.auto_paused_at}
    assert paused == {1, 2}

    action = next(a for a in outcome.actions if a.action_type == AutoActionType.PAUSE_PLATFORM.value)
    await undo_auto_action(db, action.id)
    await db.commit()
    paused = {s.id for s in (await db.execute(select(Source))).scalars() if s.auto_paused_at}
    assert paused == set()


def test_usual_interval_median():
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    times = [t0, t0 + timedelta(hours=2), t0 + timedelta(hours=4), t0 + timedelta(hours=10)]
    assert usual_interval(times) == timedelta(hours=2)
    assert usual_interval(times[:2]) is None


@pytest.mark.asyncio
async def test_stale_source_is_flagged_not_paused(db):
    db.add(_source(id=1))
    await db.commit()
    base = datetime.now(UTC) - timedelta(days=3)
    for i in range(4):
        db.add(
            SourceSyncRun(
                source_id=1,
                started_at=base + timedelta(hours=2 * i),
                finished_at=base + timedelta(hours=2 * i),
                status=SyncRunStatus.SUCCESS.value,
                fetched=3,
                new=1,
            )
        )
    await db.commit()

    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_ok(new=0, fetched=5))

    assert [a.action_type for a in outcome.actions] == [AutoActionType.FLAG_STALE.value]
    assert outcome.source.stale_flagged_at is not None
    assert outcome.source.auto_paused_at is None


@pytest.mark.asyncio
async def test_disabled_source_is_not_synced(db):
    db.add(_source(id=1, enabled=False))
    await db.commit()
    outcome = await run_source_sync(db, 1, lease_seconds=60, ingest=_ok())
    assert outcome.run is None and outcome.skipped_reason == "disabled"
