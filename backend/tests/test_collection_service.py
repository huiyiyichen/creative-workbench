"""采集页聚合（改造方案 3.8）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun, SyncRunStatus, SyncTrigger
from app.services.collection_service import (
    build_funnel,
    build_health,
    build_overview,
    is_collection_paused,
    set_collection_paused,
)
from app.services.source_sync_service import run_source_sync


def _run(source_id: int, hours_ago: float, status: str, new: int = 0, **kw) -> SourceSyncRun:
    t = datetime.now(UTC) - timedelta(hours=hours_ago)
    return SourceSyncRun(
        source_id=source_id, started_at=t, finished_at=t, status=status, fetched=new, new=new, duplicates=0, **kw
    )


@pytest.mark.asyncio
async def test_health_orders_problems_first_and_computes_rates(db):
    db.add_all(
        [
            Source(id=1, name="正常", source_type="RSS", url="https://a.example/feed", enabled=True),
            Source(id=2, name="报错", source_type="RSS", url="https://b.example/feed", enabled=True),
            Source(id=3, name="全是 0 条", source_type="RSS", url="https://c.example/feed", enabled=True),
        ]
    )
    db.add_all(
        [
            _run(1, 30, SyncRunStatus.SUCCESS.value, new=3),
            _run(1, 2, SyncRunStatus.SUCCESS.value, new=1),
            _run(2, 3, SyncRunStatus.SUCCESS.value, new=1),
            _run(2, 1, SyncRunStatus.FAILED.value, error_kind="timeout", error_message="timed out"),
            _run(3, 5, SyncRunStatus.EMPTY.value),
            _run(3, 4, SyncRunStatus.EMPTY.value),
            _run(3, 3, SyncRunStatus.EMPTY.value),
        ]
    )
    await db.commit()

    rows = await build_health(db)

    assert [r["name"] for r in rows] == ["报错", "全是 0 条", "正常"]
    by_name = {r["name"]: r for r in rows}
    assert by_name["报错"]["state"] == "error"
    assert by_name["报错"]["success_rate_7d"] == 50.0
    assert by_name["报错"]["last_error"]["kind"] == "timeout"
    assert by_name["全是 0 条"]["state"] == "empty"
    assert by_name["正常"]["success_rate_7d"] == 100.0
    assert sum(by_name["正常"]["daily_new"]) == 4
    assert len(by_name["正常"]["daily_new"]) == 7


@pytest.mark.asyncio
async def test_overview_keeps_missing_values_empty(db):
    overview = await build_overview(db)
    assert overview["success_rate_7d"]["value"] is None
    assert overview["analysis_cost_today"]["value"] is None
    assert overview["missed"]["value"] is None
    assert overview["today_new"]["value"] == 0


@pytest.mark.asyncio
async def test_funnel_sums_runs(db):
    db.add(Source(id=1, name="s", source_type="RSS", url="https://a.example/feed", enabled=True))
    db.add(_run(1, 1, SyncRunStatus.SUCCESS.value, new=2))
    await db.commit()
    funnel = await build_funnel(db)
    stages = {s["key"]: s for s in funnel["stages"]}
    assert stages["fetched"]["value"] == 2
    assert stages["quick"]["value"] == 0 and stages["triage"]["threshold"] == 35.0
    assert funnel["budget"] == {"budget": 5.0, "spent": 0.0, "remaining": 5.0}


@pytest.mark.asyncio
async def test_global_pause_skips_scheduled_but_not_manual(db):
    db.add(Source(id=1, name="s", source_type="RSS", url="https://a.example/feed", enabled=True))
    await db.commit()
    await set_collection_paused(db, True)
    assert await is_collection_paused(db)

    async def ingest(source, db):
        return {"fetched": 1, "new": 1, "duplicates": 0}

    skipped = await run_source_sync(db, 1, lease_seconds=60, ingest=ingest)
    assert skipped.run is None and skipped.skipped_reason == "collection_paused"
    manual = await run_source_sync(db, 1, trigger=SyncTrigger.MANUAL, lease_seconds=60, ingest=ingest)
    assert manual.run is not None
