"""采集页（改造方案 3.8）：健康、流程、关键数字、处理记录。

数据全部来自 ``source_sync_runs``、``content_items``、模型调用记录；
没有数据的指标返回 None（界面显示「—」），不记 0。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_backend import ensure_aware_utc
from app.models.source import Source, SourceStatus
from app.models.source_sync_run import SourceSyncRun, SyncRunStatus
from app.repositories.app_setting_repo import AppSettingRepository
from app.repositories.collection_repo import CollectionStatsRepository
from app.repositories.source_sync_run_repo import AutoActionRepository

COLLECTION_PAUSED_KEY = "collection_paused"
HEALTH_DAYS = 7


# ── 全局暂停（托盘「暂停采集」） ─────────────────────────────────────


async def is_collection_paused(db: AsyncSession) -> bool:
    row = await AppSettingRepository(db).get_by_key(COLLECTION_PAUSED_KEY)
    return bool(row and row.value == "1")


async def set_collection_paused(db: AsyncSession, paused: bool) -> bool:
    await AppSettingRepository(db).upsert_setting(
        COLLECTION_PAUSED_KEY, "1" if paused else "0", "托盘 / 采集页的全局暂停开关"
    )
    await db.commit()
    return paused


# ── 健康 ─────────────────────────────────────────────────────────────


def _rate(ok: int, total: int) -> float | None:
    return round(ok / total * 100, 1) if total else None


def _next_run(source: Source, scheduled: dict[int, datetime]) -> datetime | None:
    if not source.enabled:
        return None
    if source.id in scheduled:
        return scheduled[source.id]
    last = ensure_aware_utc(source.last_sync_at)
    if last is None:
        return None
    return last + timedelta(minutes=int(source.fetch_interval_minutes or 60))


def _scheduled_next_runs() -> dict[int, datetime]:
    """读调度器里每个信源任务的下次运行时间；调度器未运行时为空。"""
    try:
        from app.scheduler import scheduler
    except Exception:  # pragma: no cover - 导入失败只影响「下次计划」一列
        return {}
    if not scheduler.running:
        return {}
    out: dict[int, datetime] = {}
    for job in scheduler.get_jobs():
        if job.id.startswith("source_sync_") and job.next_run_time is not None:
            try:
                out[int(job.id.removeprefix("source_sync_"))] = job.next_run_time.astimezone(UTC)
            except ValueError:
                continue
    return out


def health_state(source: Source, runs: list[SourceSyncRun]) -> str:
    """一个信源的综合状态，异常排前：paused > error > stale > empty > ok > idle / disabled。"""
    if not source.enabled or source.status == SourceStatus.DISABLED:
        return "disabled"
    if source.auto_paused_at is not None:
        return "paused"
    if source.status == SourceStatus.ERROR or (runs and runs[-1].status == SyncRunStatus.FAILED.value):
        return "error"
    if source.stale_flagged_at is not None:
        return "stale"
    finished = [r for r in runs if r.status in (SyncRunStatus.SUCCESS.value, SyncRunStatus.EMPTY.value)]
    # 连续多次 0 条但不报错也算异常（3.8）
    if len(finished) >= 3 and all((r.new or 0) == 0 for r in finished[-3:]):
        return "empty"
    if not runs:
        return "idle"
    return "ok"


_STATE_ORDER = {"paused": 0, "error": 1, "stale": 2, "empty": 3, "idle": 4, "ok": 5, "disabled": 6}


async def build_health(db: AsyncSession, *, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    repo = CollectionStatsRepository(db)
    since = now - timedelta(days=HEALTH_DAYS)
    sources = await repo.list_sources()
    runs_by_source: dict[int, list[SourceSyncRun]] = defaultdict(list)
    for run in await repo.runs_since(since):
        runs_by_source[run.source_id].append(run)
    scheduled = _scheduled_next_runs()
    day0 = (now - timedelta(days=HEALTH_DAYS - 1)).date()

    rows: list[dict[str, Any]] = []
    for source in sources:
        runs = runs_by_source.get(source.id, [])
        done = [r for r in runs if r.status != SyncRunStatus.RUNNING.value]
        ok = [r for r in done if r.status != SyncRunStatus.FAILED.value]
        last_ok = max((ensure_aware_utc(r.finished_at) for r in ok if r.finished_at), default=None)
        last_fail = next((r for r in reversed(done) if r.status == SyncRunStatus.FAILED.value), None)
        daily = [0] * HEALTH_DAYS
        for r in ok:
            started = ensure_aware_utc(r.started_at)
            idx = (started.date() - day0).days if started else -1
            if 0 <= idx < HEALTH_DAYS:
                daily[idx] += int(r.new or 0)
        state = health_state(source, done)
        rows.append(
            {
                "id": source.id,
                "name": source.name,
                "platform": source.platform,
                "kind": source.kind,
                "query": source.query,
                "platforms": source.platforms,
                "source_type": str(getattr(source.source_type, "value", source.source_type)),
                "url": source.url,
                "enabled": bool(source.enabled),
                "state": state,
                "interval_minutes": int(source.fetch_interval_minutes or 60),
                "base_interval_minutes": source.base_interval_minutes,
                "auto_paused_at": source.auto_paused_at,
                "auto_pause_reason": source.auto_pause_reason,
                "consecutive_failures": int(source.consecutive_failures or 0),
                "last_success_at": last_ok,
                "next_run_at": _next_run(source, scheduled),
                "success_rate_7d": _rate(len(ok), len(done)),
                "runs_7d": len(done),
                "last_error": (
                    {
                        "kind": last_fail.error_kind,
                        "message": last_fail.error_message,
                        "at": last_fail.started_at,
                        "http_status": last_fail.http_status,
                    }
                    if last_fail
                    else None
                ),
                "daily_new": daily,
            }
        )
    rows.sort(key=lambda r: (_STATE_ORDER.get(r["state"], 9), r["name"]))
    return rows


# ── 关键数字（与 7 天前对比） ────────────────────────────────────────


def _day_start(now: datetime) -> datetime:
    local = now.astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


async def build_overview(db: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    repo = CollectionStatsRepository(db)
    today = _day_start(now)
    week_ago = today - timedelta(days=7)
    runs = await repo.runs_since(today - timedelta(days=14))

    def success_rate(start: datetime, end: datetime) -> float | None:
        window = [
            r for r in runs if r.status != SyncRunStatus.RUNNING.value and start <= ensure_aware_utc(r.started_at) < end
        ]
        return _rate(sum(1 for r in window if r.status != SyncRunStatus.FAILED.value), len(window))

    return {
        "today_new": {
            "value": await repo.count_crawled_between(today, now),
            "previous": await repo.count_crawled_between(week_ago, week_ago + (now - today)),
        },
        "success_rate_7d": {
            "value": success_rate(now - timedelta(days=7), now),
            "previous": success_rate(now - timedelta(days=14), now - timedelta(days=7)),
        },
        "pending_analysis": {"value": await repo.count_pending_analysis(), "previous": None},
        "analysis_cost_today": {
            "value": await repo.llm_cost_between(today, now),
            "previous": await repo.llm_cost_between(week_ago, week_ago + (now - today)),
        },
        # 漏采数依赖热榜对照（阶段 2），这里先保持空值
        "missed": {"value": None, "previous": None},
        "paused": await is_collection_paused(db),
    }


# ── 流程漏斗 ─────────────────────────────────────────────────────────


async def build_funnel(db: AsyncSession, *, days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    """采到 → 去重 → 预筛（按原因）→ 初筛 → 快速判断 → 完整分析 → 精选（改造方案 3.8 / 4.1）。"""
    from app.services.analysis_funnel import budget_status, load_funnel_settings

    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    repo = CollectionStatsRepository(db)
    runs = [r for r in await repo.runs_since(since) if r.status != SyncRunStatus.RUNNING.value]
    fetched = sum(int(r.fetched or 0) for r in runs)
    duplicates = sum(int(r.duplicates or 0) for r in runs)
    new = sum(int(r.new or 0) for r in runs)
    skipped = await repo.skip_reason_counts_since(since)
    statuses = await repo.status_counts_since(since)
    cfg = await load_funnel_settings(db)
    levels = await repo.funnel_counts_since(since, triage_threshold=cfg.triage_threshold)
    prefilter_pass = max(sum(statuses.values()) - sum(skipped.values()), 0)
    return {
        "days": days,
        "stages": [
            {"key": "fetched", "label": "采到", "value": fetched if runs else None},
            {"key": "deduped", "label": "去重后", "value": new if runs else None, "removed": duplicates},
            {"key": "prefilter", "label": "预筛通过", "value": prefilter_pass, "removed_by_reason": skipped},
            {"key": "triage", "label": "初筛过线", "value": levels["triaged"], "threshold": cfg.triage_threshold},
            {"key": "quick", "label": "快速判断", "value": levels["quick"], "passed": levels["quick_pass"]},
            {"key": "full", "label": "完整分析", "value": levels["full"]},
            {"key": "picked", "label": "精选", "value": levels["picked"]},
        ],
        "backlog": {
            "pending": statuses.get("pending", 0),
            "analyzing": statuses.get("analyzing", 0),
            "error": statuses.get("error", 0),
        },
        "budget": await budget_status(db, cfg),
    }


# ── 处理记录 ─────────────────────────────────────────────────────────


async def list_auto_actions(db: AsyncSession, *, limit: int = 50) -> list[dict[str, Any]]:
    actions = await AutoActionRepository(db).list_recent(limit=limit)
    return [
        {
            "id": a.id,
            "action_type": a.action_type,
            "target_type": a.target_type,
            "target_id": a.target_id,
            "target_label": a.target_label,
            "reason": a.reason,
            "executed_at": a.executed_at,
            "undone_at": a.undone_at,
            "undoable": a.undone_at is None,
        }
        for a in actions
    ]


# ── 最近采到（阶段 1：封面与观测曲线） ─────────────────────────────


async def list_source_recent(db: AsyncSession, source_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
    from app.repositories.content_journey_repo import SourceRecentRepository

    repo = SourceRecentRepository(db)
    rows = await repo.recent(source_id, limit=limit)
    ids = [item.id for item, _, _ in rows]
    series: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for obs in await repo.series_for(ids):
        series.setdefault(obs.content_id, {}).setdefault(obs.metric, []).append(
            {"at": obs.observed_at, "value": obs.value}
        )
    out = []
    for item, color, asset_status in rows:
        media = item.media or {}
        item_series = series.get(item.id, {})
        out.append(
            {
                "id": item.id,
                "title": item.title,
                "url": item.url,
                "platform": item.platform,
                "media_type": item.media_type,
                "author": item.author,
                "published_at": item.published_at,
                "crawled_at": item.crawled_at,
                "cover_url": item.cover_url,
                "cover_asset_id": item.cover_asset_id if asset_status == "ready" else None,
                "cover_color": color,
                "duration": media.get("duration"),
                "orientation": media.get("orientation"),
                "triage_score": item.triage_score,
                "analysis_level": item.analysis_level,
                "full_eligible": item.full_eligible,
                "latest": {metric: points[-1]["value"] for metric, points in item_series.items()},
                "series": item_series,
            }
        )
    return out
