"""信源同步入口：记录每次运行（source_sync_runs）并执行自动处理（auto_actions）。

调度器、手动同步、启动补采都走 :func:`run_source_sync`，保证每次同步都有一行记录。
自动处理规则见改造方案 3.9：

* 连续失败 3 次 → 暂停该信源；之后每 6 小时重试一次，成功后自动恢复。
* 登录失效 / 验证码 → 暂停同平台全部信源，等用户处理后恢复（撤销）。
* 限流（429 等）→ 间隔翻倍（上限 24 小时）；恢复正常后逐次减半回到原间隔。
* 不报错但超过平常间隔 3 倍没有新内容 → 标记「可能失效」并通知，不暂停。

只做能撤销的保护动作；撤销按 ``previous_state`` 恢复原状态。
"""

from __future__ import annotations

import logging
import re
import statistics
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auto_action import AutoAction, AutoActionType
from app.models.source import Source, SourceStatus
from app.models.source_sync_run import SourceSyncRun, SyncErrorKind, SyncRunStatus, SyncTrigger
from app.repositories.source_repo import SourceRepository
from app.repositories.source_sync_run_repo import AutoActionRepository, SourceSyncRunRepository

logger = logging.getLogger(__name__)

FAILURE_PAUSE_THRESHOLD = 3
PAUSED_RETRY_INTERVAL = timedelta(hours=6)
MAX_BACKOFF_MINUTES = 24 * 60
STALE_FACTOR = 3
STALE_LOOKBACK = timedelta(days=30)
STALE_MIN_SAMPLES = 3


# ── 错误分类 ──────────────────────────────────────────────────────────

# httpx 的错误信息形如 "Client error '429 Too Many Requests' for url ..."；
# 只认后面跟空格 / 引号 / 结尾的三位数，避免把 "timed out after 450s" 当成状态码。
_HTTP_STATUS_RE = re.compile(r"(?<![\d.])([45]\d\d)(?=[ '\")]|$)")

_KIND_PATTERNS: list[tuple[SyncErrorKind, re.Pattern[str]]] = [
    (SyncErrorKind.CAPTCHA, re.compile(r"captcha|验证码|人机验证|滑块", re.I)),
    (SyncErrorKind.LOGIN, re.compile(r"登录|login|cookie.*(失效|expired)|unauthori[sz]ed|\b401\b|未登录", re.I)),
    (SyncErrorKind.RATE_LIMIT, re.compile(r"\b429\b|rate.?limit|too many requests|限流|频率", re.I)),
    (SyncErrorKind.TIMEOUT, re.compile(r"time(d)?\s?out|超时", re.I)),
    (SyncErrorKind.BLOCKED, re.compile(r"\b403\b|forbidden|ssrf|unsafe|内网|blocked", re.I)),
    (
        SyncErrorKind.API_CHANGED,
        re.compile(r"\b(404|410)\b|parse|解析|schema|keyerror|jsondecode|no scraper registered|接口", re.I),
    ),
]


def classify_sync_error(message: str | None) -> tuple[SyncErrorKind, int | None]:
    """把同步错误信息归到 3.3 规定的错误类型，并尽量提取 HTTP 状态码。"""
    text = message or ""
    http_status: int | None = None
    for match in _HTTP_STATUS_RE.finditer(text):
        code = int(match.group(1))
        if 400 <= code <= 599:
            http_status = code
            break
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(text):
            return kind, http_status
    return SyncErrorKind.OTHER, http_status


# ── 结果 ─────────────────────────────────────────────────────────────


@dataclass
class SyncOutcome:
    source: Source | None
    run: SourceSyncRun | None
    stats: dict[str, Any] = field(default_factory=dict)
    skipped_reason: str | None = None
    actions: list[AutoAction] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.run is not None and self.run.status == SyncRunStatus.FAILED.value


def paused_retry_due(source: Source, now: datetime | None = None) -> bool:
    """自动暂停的信源每 6 小时重试一次。"""
    if source.auto_paused_at is None:
        return True
    now = now or datetime.now(UTC)
    anchor = max(_aware(source.auto_paused_at), _aware(source.last_sync_at) if source.last_sync_at else _MIN)
    return now - anchor >= PAUSED_RETRY_INTERVAL


_MIN = datetime(1970, 1, 1, tzinfo=UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def run_source_sync(
    db: AsyncSession,
    source_id: int,
    *,
    trigger: SyncTrigger = SyncTrigger.SCHEDULE,
    lease_seconds: int,
    is_backfill: bool = False,
    respect_auto_pause: bool = True,
    ingest: Callable[[Source, AsyncSession], Awaitable[dict[str, Any]]] | None = None,
) -> SyncOutcome:
    """认领、抓取、记录、执行自动处理。调用方负责最外层 commit 之外的事。

    返回 ``SyncOutcome``；``run`` 为 None 表示本次没有实际抓取（被他人占用、
    已停用、或处于自动暂停且未到重试时间）。
    """
    if ingest is None:
        from app.services.content_pipeline import ingest_from_source as ingest

    repo = SourceRepository(db)
    current = await repo.get_by_id(source_id)
    if current is None or not current.enabled:
        return SyncOutcome(source=current, run=None, skipped_reason="disabled")
    if trigger != SyncTrigger.MANUAL:
        from app.services.collection_service import is_collection_paused

        if await is_collection_paused(db):
            return SyncOutcome(source=current, run=None, skipped_reason="collection_paused")
    if respect_auto_pause and current.auto_paused_at is not None and trigger != SyncTrigger.MANUAL:
        if not paused_retry_due(current):
            return SyncOutcome(source=current, run=None, skipped_reason="auto_paused")
        trigger = SyncTrigger.RETRY

    source = await repo.claim_sync(source_id, lease_seconds=lease_seconds)
    await db.commit()
    if source is None:
        return SyncOutcome(source=None, run=None, skipped_reason="lease_active")

    run_repo = SourceSyncRunRepository(db)
    run = await run_repo.add(
        SourceSyncRun(
            source_id=source_id,
            trigger=trigger.value,
            started_at=datetime.now(UTC),
            status=SyncRunStatus.RUNNING.value,
            is_backfill=is_backfill,
        )
    )
    await db.commit()
    run_id = run.id

    started = time.perf_counter()
    stats: dict[str, Any] = {"fetched": 0, "new": 0, "duplicates": 0}
    crash: str | None = None
    try:
        stats = await ingest(source, db)
        await db.commit()
    except Exception as exc:  # ingest 自己会兜底；这里防御意外异常，保证记录完整
        crash = str(exc) or exc.__class__.__name__
        logger.exception("source %d sync crashed", source_id)
        await db.rollback()

    duration_ms = int((time.perf_counter() - started) * 1000)
    source = await repo.get_by_id(source_id)
    run = await run_repo.get_by_id(run_id)
    if source is None or run is None:  # 信源在同步期间被删除
        return SyncOutcome(source=source, run=run, stats=stats)
    await db.refresh(source)

    error_message = crash or (source.sync_error if source.status == SourceStatus.ERROR else None)
    run.finished_at = datetime.now(UTC)
    run.duration_ms = duration_ms
    run.fetched = int(stats.get("fetched") or 0)
    run.new = int(stats.get("new") or 0)
    run.duplicates = int(stats.get("duplicates") or 0)
    skipped = stats.get("skipped") or None
    run.skipped = dict(skipped) if skipped else None
    if error_message:
        from app.services._error_redaction import redact_source_sync_error

        kind, http_status = classify_sync_error(error_message)
        run.status = SyncRunStatus.FAILED.value
        run.error_kind = kind.value
        run.error_message = redact_source_sync_error(error_message)[:500]
        run.http_status = http_status
        if crash and source.status != SourceStatus.ERROR:
            source.status = SourceStatus.ERROR
            source.sync_error = run.error_message
            source.last_sync_at = datetime.now(UTC)
    else:
        run.status = SyncRunStatus.SUCCESS.value if run.fetched else SyncRunStatus.EMPTY.value

    actions = await apply_auto_actions(db, source, run)
    await db.commit()
    await notify_auto_actions(actions)
    return SyncOutcome(source=source, run=run, stats=stats, actions=actions)


# ── 自动处理 ─────────────────────────────────────────────────────────


async def apply_auto_actions(db: AsyncSession, source: Source, run: SourceSyncRun) -> list[AutoAction]:
    """根据刚结束的一次运行执行 3.9 的自动处理，返回新写入的记录。"""
    actions: list[AutoAction] = []
    action_repo = AutoActionRepository(db)
    now = datetime.now(UTC)

    if run.status == SyncRunStatus.FAILED.value:
        source.consecutive_failures = int(source.consecutive_failures or 0) + 1
        kind = run.error_kind

        if kind in (SyncErrorKind.LOGIN.value, SyncErrorKind.CAPTCHA.value) and source.platform:
            action = await _pause_platform(db, source, kind, now)
            if action is not None:
                actions.append(action)
        elif kind == SyncErrorKind.RATE_LIMIT.value:
            actions.append(await _backoff(db, source, now))
        if source.consecutive_failures >= FAILURE_PAUSE_THRESHOLD and source.auto_paused_at is None:
            previous = {"auto_paused_at": None, "auto_pause_reason": None}
            source.auto_paused_at = now
            source.auto_pause_reason = f"连续失败 {source.consecutive_failures} 次"
            actions.append(
                await action_repo.add(
                    AutoAction(
                        action_type=AutoActionType.PAUSE_SOURCE.value,
                        target_type="source",
                        target_id=str(source.id),
                        target_label=source.name,
                        reason=f"连续失败 {source.consecutive_failures} 次（最近：{_kind_label(kind)}），"
                        "已暂停，之后每 6 小时重试一次",
                        previous_state=previous,
                        executed_at=now,
                    )
                )
            )
        return actions

    # 成功（含 0 条）
    source.consecutive_failures = 0
    if source.auto_paused_at is not None and (source.auto_pause_reason or "").startswith("连续失败"):
        previous = {
            "auto_paused_at": source.auto_paused_at.isoformat(),
            "auto_pause_reason": source.auto_pause_reason,
        }
        source.auto_paused_at = None
        source.auto_pause_reason = None
        actions.append(
            await action_repo.add(
                AutoAction(
                    action_type=AutoActionType.RESUME_SOURCE.value,
                    target_type="source",
                    target_id=str(source.id),
                    target_label=source.name,
                    reason="暂停后的重试成功，已自动恢复",
                    previous_state=previous,
                    executed_at=now,
                )
            )
        )
    if source.base_interval_minutes:
        # 限流恢复：逐次减半回到原间隔
        source.fetch_interval_minutes = max(source.base_interval_minutes, int(source.fetch_interval_minutes) // 2)
        if source.fetch_interval_minutes <= source.base_interval_minutes:
            source.fetch_interval_minutes = source.base_interval_minutes
            source.base_interval_minutes = None

    if (run.new or 0) > 0:
        source.stale_flagged_at = None
    else:
        action = await _maybe_flag_stale(db, source, now)
        if action is not None:
            actions.append(action)
    return actions


async def _pause_platform(db: AsyncSession, source: Source, kind: str | None, now: datetime) -> AutoAction | None:
    action_repo = AutoActionRepository(db)
    platform = source.platform or ""
    if await action_repo.latest_open_for("platform", platform, AutoActionType.PAUSE_PLATFORM.value):
        # 已暂停过：只把当前信源也挂上暂停
        if source.auto_paused_at is None:
            source.auto_paused_at = now
            source.auto_pause_reason = f"{platform} {_kind_label(kind)}"
        return None
    siblings = await SourceRepository(db).list_enabled_by_platform(platform)
    affected = [s for s in siblings if s.auto_paused_at is None]
    if source not in affected and source.auto_paused_at is None:
        affected.append(source)
    for s in affected:
        s.auto_paused_at = now
        s.auto_pause_reason = f"{platform} {_kind_label(kind)}"
    return await action_repo.add(
        AutoAction(
            action_type=AutoActionType.PAUSE_PLATFORM.value,
            target_type="platform",
            target_id=platform,
            target_label=platform,
            reason=f"{source.name}：{_kind_label(kind)}，已暂停该平台 {len(affected)} 个信源，处理后点撤销恢复",
            previous_state={"source_ids": [s.id for s in affected]},
            executed_at=now,
        )
    )


async def _backoff(db: AsyncSession, source: Source, now: datetime) -> AutoAction:
    current = int(source.fetch_interval_minutes or 60)
    previous = {"fetch_interval_minutes": current, "base_interval_minutes": source.base_interval_minutes}
    if source.base_interval_minutes is None:
        source.base_interval_minutes = current
    source.fetch_interval_minutes = min(current * 2, MAX_BACKOFF_MINUTES)
    return await AutoActionRepository(db).add(
        AutoAction(
            action_type=AutoActionType.BACKOFF_SOURCE.value,
            target_type="source",
            target_id=str(source.id),
            target_label=source.name,
            reason=f"被平台限流，同步间隔 {current} → {source.fetch_interval_minutes} 分钟，恢复后逐步回到原间隔",
            previous_state=previous,
            executed_at=now,
        )
    )


def usual_interval(run_times: list[datetime]) -> timedelta | None:
    """平常间隔：近 30 天相邻两次有新增的中位间隔（3.8 口径）。"""
    if len(run_times) < STALE_MIN_SAMPLES:
        return None
    ordered = sorted(_aware(t) for t in run_times)
    gaps = [(b - a).total_seconds() for a, b in zip(ordered, ordered[1:], strict=False) if b > a]
    if not gaps:
        return None
    return timedelta(seconds=statistics.median(gaps))


async def _maybe_flag_stale(db: AsyncSession, source: Source, now: datetime) -> AutoAction | None:
    if source.stale_flagged_at is not None:
        return None
    run_times = await SourceSyncRunRepository(db).productive_run_times(source.id, now - STALE_LOOKBACK)
    interval = usual_interval(run_times)
    if interval is None:
        return None
    last_new = _aware(run_times[-1])
    if now - last_new <= interval * STALE_FACTOR:
        return None
    source.stale_flagged_at = now
    days = (now - last_new).total_seconds() / 86400
    return await AutoActionRepository(db).add(
        AutoAction(
            action_type=AutoActionType.FLAG_STALE.value,
            target_type="source",
            target_id=str(source.id),
            target_label=source.name,
            reason=f"没有报错，但已 {days:.1f} 天没有新内容（平常约 {interval.total_seconds() / 3600:.1f} 小时一次），"
            "可能已失效",
            previous_state={"stale_flagged_at": None},
            executed_at=now,
        )
    )


def _kind_label(kind: str | None) -> str:
    return {
        SyncErrorKind.LOGIN.value: "登录失效",
        SyncErrorKind.CAPTCHA.value: "出现验证码",
        SyncErrorKind.RATE_LIMIT.value: "被限流",
        SyncErrorKind.TIMEOUT.value: "超时",
        SyncErrorKind.API_CHANGED.value: "接口变化",
        SyncErrorKind.BLOCKED.value: "被拒绝访问",
    }.get(kind or "", "其他错误")


# ── 撤销 ─────────────────────────────────────────────────────────────


class AutoActionUndoError(Exception):
    pass


async def undo_auto_action(db: AsyncSession, action_id: int) -> AutoAction:
    """撤销一条自动处理，恢复原状态。"""
    action_repo = AutoActionRepository(db)
    action = await action_repo.get_by_id(action_id)
    if action is None:
        raise AutoActionUndoError("记录不存在")
    if action.undone_at is not None:
        raise AutoActionUndoError("这条处理已撤销")
    source_repo = SourceRepository(db)
    prev = action.previous_state or {}

    if action.action_type == AutoActionType.PAUSE_PLATFORM.value:
        for sid in prev.get("source_ids", []):
            s = await source_repo.get_by_id(int(sid))
            if s is not None:
                s.auto_paused_at = None
                s.auto_pause_reason = None
                s.consecutive_failures = 0
    else:
        source = await source_repo.get_by_id(int(action.target_id))
        if source is not None:
            if action.action_type == AutoActionType.PAUSE_SOURCE.value:
                source.auto_paused_at = None
                source.auto_pause_reason = None
                source.consecutive_failures = 0
            elif action.action_type == AutoActionType.BACKOFF_SOURCE.value:
                source.fetch_interval_minutes = int(prev.get("fetch_interval_minutes") or source.fetch_interval_minutes)
                source.base_interval_minutes = prev.get("base_interval_minutes")
            elif action.action_type == AutoActionType.FLAG_STALE.value:
                source.stale_flagged_at = None
            elif action.action_type == AutoActionType.RESUME_SOURCE.value:
                paused_at = prev.get("auto_paused_at")
                source.auto_paused_at = datetime.fromisoformat(paused_at) if paused_at else datetime.now(UTC)
                source.auto_pause_reason = prev.get("auto_pause_reason")
    action.undone_at = datetime.now(UTC)
    await db.flush()
    return action


async def notify_auto_actions(actions: list[AutoAction]) -> None:
    """自动处理事后通知（站内通知；托盘程序轮询后转成 Windows 通知）。"""
    if not actions:
        return
    from app.services.notification_service import push_notification

    for action in actions:
        if action.action_type == AutoActionType.RESUME_SOURCE.value:
            title = f"已恢复：{action.target_label}"
        elif action.action_type == AutoActionType.FLAG_STALE.value:
            title = f"可能失效：{action.target_label}"
        else:
            title = f"已自动处理：{action.target_label}"
        try:
            await push_notification("auto_action", "collection", title, action.reason)
        except Exception:
            logger.warning("auto action notification failed", exc_info=True)
