"""趋势计算 v2（改造方案 5.3）。

话题单位：事件（4.1 归并结果）和追踪词。每小时增量计算，结果写入扩展后的 ``topic_trends``
（``calculation_version = "signal-v2"``，每个话题每天一行，同一天内覆盖更新）。

每小时信号：
* 该小时发布（缺失时用采集时间）的条目，每条 1 分；
* 平台指标增量：同一指标相邻两次观测的增量 Δ，记在后一次观测的小时，贡献 ``0.5 × log10(1 + Δ)``；
* 上榜：每次排名观测贡献 ``(51 − 排名) / 50``（前 50 名）。

没有任何成功同步、也没有条目的小时记为 ``None``（观测不足），不画 0。

状态（阈值可调，``DEFAULT_STATUS_RULES``）：
* ``new`` 新出现：首次出现不足 24 小时；
* ``rising`` 升温：近 24 小时信号比前 24 小时增长 ≥ 50%；
* ``cooling`` 降温：近 24 小时比峰值 24 小时下降 ≥ 50%；
* ``peak`` 见顶：增速转负但仍在高位（≥ 峰值的 50%）；
* ``steady`` 持续：连续 3 天以上有信号；
* ``quiet``：以上都不是。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_event import ContentEventGroup, ContentEventMember
from app.models.content_observation import ContentMetricObservation
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun
from app.models.trend import TopicTrend

CALC_VERSION = "signal-v2"
WINDOW_HOURS = 7 * 24  # 只扫描最近 7 天的观测窗口
SERIES_HOURS = 72  # 存储的逐小时曲线长度

STATUS_LABEL = {
    "new": "新出现",
    "rising": "升温",
    "steady": "持续",
    "peak": "见顶",
    "cooling": "降温",
    "quiet": "平静",
}

DEFAULT_STATUS_RULES: dict[str, float] = {
    "new_hours": 24,
    "rising_ratio": 0.5,
    "cooling_ratio": 0.5,
    "steady_days": 3,
}

PRIMARY_METRICS = ("views", "stars", "score", "hot", "likes", "favorites", "comments")


@dataclass
class MemberFacts:
    content_id: int
    platform: str | None
    source_id: int | None
    ts: datetime
    observations: list[tuple[str, datetime, float]] = field(default_factory=list)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _hour(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def hourly_signal(
    members: list[MemberFacts],
    *,
    observed_hours: set[datetime],
    end: datetime,
    hours: int,
) -> list[float | None]:
    """返回 ``hours`` 个小时桶（最旧在前、最新在后）；没有观测的小时为 None。"""
    end_h = _hour(end)
    start_h = end_h - timedelta(hours=hours - 1)
    buckets: dict[datetime, float] = defaultdict(float)
    touched: set[datetime] = set()

    for m in members:
        h = _hour(m.ts)
        if start_h <= h <= end_h:
            buckets[h] += 1.0
            touched.add(h)
        by_metric: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for metric, at, value in m.observations:
            by_metric[metric].append((at, value))
        for metric, rows in by_metric.items():
            rows.sort(key=lambda r: r[0])
            if metric == "rank":
                for at, value in rows:
                    h = _hour(at)
                    if start_h <= h <= end_h and 0 < value <= 50:
                        buckets[h] += (51 - value) / 50
                        touched.add(h)
                continue
            if metric not in PRIMARY_METRICS:
                continue
            for (_, prev), (at, cur) in zip(rows, rows[1:], strict=False):
                h = _hour(at)
                delta = cur - prev
                if start_h <= h <= end_h and delta > 0:
                    buckets[h] += 0.5 * math.log10(1 + delta)
                    touched.add(h)

    out: list[float | None] = []
    for i in range(hours):
        h = start_h + timedelta(hours=i)
        if h in touched:
            out.append(round(buckets[h], 3))
        elif h in observed_hours:
            out.append(0.0)
        else:
            out.append(None)
    return out


def _sum(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def classify_status(
    series: list[float | None],
    *,
    first_seen: datetime,
    now: datetime,
    rules: dict[str, float] | None = None,
) -> tuple[str, dict[str, Any]]:
    """``series`` 为逐小时信号（最新在后），长度应 ≥ 48。"""
    r = {**DEFAULT_STATUS_RULES, **(rules or {})}
    last24 = _sum(series[-24:])
    prev24 = _sum(series[-48:-24])
    windows = [_sum(series[i : i + 24]) for i in range(0, max(1, len(series) - 23))]
    peak24 = max((w for w in windows if w is not None), default=None)
    days_with_signal = 0
    streak = 0
    for d in range(len(series) // 24):
        chunk = series[len(series) - 24 * (d + 1) : len(series) - 24 * d]
        if (_sum(chunk) or 0) > 0:
            streak += 1
            days_with_signal = max(days_with_signal, streak)
        else:
            break
    info = {
        "last24": last24,
        "prev24": prev24,
        "peak24": peak24,
        "streak_days": days_with_signal,
    }
    age_h = (now - first_seen).total_seconds() / 3600
    if age_h < r["new_hours"]:
        return "new", info
    if last24 is None:
        return "quiet", info
    if prev24 is not None and prev24 > 0 and (last24 - prev24) / prev24 >= r["rising_ratio"]:
        return "rising", info
    if prev24 == 0 and last24 > 0:
        return "rising", info
    if peak24 and last24 <= peak24 * (1 - r["cooling_ratio"]):
        return "cooling", info
    if prev24 is not None and last24 < prev24 and peak24 and last24 >= peak24 * 0.5:
        return "peak", info
    if days_with_signal >= r["steady_days"]:
        return "steady", info
    return "quiet", info


# ── 数据库 ────────────────────────────────────────────────────────


async def _observed_hours(db: AsyncSession, since: datetime) -> set[datetime]:
    rows = (
        await db.execute(
            select(SourceSyncRun.finished_at).where(
                SourceSyncRun.finished_at >= since, SourceSyncRun.status.in_(("success", "empty"))
            )
        )
    ).scalars()
    return {_hour(ts) for ts in rows if ts is not None}


async def _member_facts(db: AsyncSession, content_ids: list[int], since: datetime) -> dict[int, MemberFacts]:
    if not content_ids:
        return {}
    items = (
        await db.execute(
            select(
                ContentItem.id,
                ContentItem.platform,
                ContentItem.source_id,
                func.coalesce(ContentItem.published_at, ContentItem.crawled_at),
            ).where(ContentItem.id.in_(content_ids))
        )
    ).all()
    facts = {cid: MemberFacts(cid, platform, source_id, _aware(ts)) for cid, platform, source_id, ts in items}
    obs = (
        await db.execute(
            select(
                ContentMetricObservation.content_id,
                ContentMetricObservation.metric,
                ContentMetricObservation.observed_at,
                ContentMetricObservation.value,
            ).where(
                ContentMetricObservation.content_id.in_(content_ids),
                ContentMetricObservation.observed_at >= since - timedelta(days=1),
            )
        )
    ).all()
    for cid, metric, at, value in obs:
        if cid in facts:
            facts[cid].observations.append((metric, _aware(at), float(value)))
    return facts


async def _event_topics(db: AsyncSession, since: datetime) -> list[dict[str, Any]]:
    groups = (
        (
            await db.execute(
                select(ContentEventGroup).where(
                    ContentEventGroup.last_occurrence_at >= since,
                    ContentEventGroup.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    if not groups:
        return []
    ids = [g.id for g in groups]
    members = (
        await db.execute(
            select(ContentEventMember.event_group_id, ContentEventMember.content_id).where(
                ContentEventMember.event_group_id.in_(ids),
                ContentEventMember.review_status != "rejected",
            )
        )
    ).all()
    by_group: dict[int, list[int]] = defaultdict(list)
    for gid, cid in members:
        by_group[gid].append(cid)
    rep_ids = {g.id: g.representative_content_id or g.canonical_content_id for g in groups}
    titles = dict(
        (
            await db.execute(select(ContentItem.id, ContentItem.title).where(ContentItem.id.in_(set(rep_ids.values()))))
        ).all()
    )
    return [
        {
            "kind": "event",
            "event_group_id": g.id,
            "title": titles.get(rep_ids[g.id], f"事件 {g.id}"),
            "content_ids": sorted(set(by_group.get(g.id, [])) | {g.canonical_content_id}),
            "representative_content_id": rep_ids[g.id],
            "first_seen": g.first_occurrence_at,
        }
        for g in groups
    ]


async def _watch_term_topics(db: AsyncSession, since: datetime) -> list[dict[str, Any]]:
    terms = (await db.execute(select(Source).where(Source.kind == "keyword", Source.enabled.is_(True)))).scalars().all()
    topics: list[dict[str, Any]] = []
    for src in terms:
        term = (src.query or src.keyword or src.name or "").strip()
        if not term:
            continue
        own = select(ContentItem.id).where(
            ContentItem.source_id == src.id,
            func.coalesce(ContentItem.published_at, ContentItem.crawled_at) >= since,
        )
        hit = select(ContentItem.id).where(
            func.coalesce(ContentItem.published_at, ContentItem.crawled_at) >= since,
            ContentItem.title.ilike(f"%{term}%"),
        )
        ids = set((await db.execute(own)).scalars()) | set((await db.execute(hit)).scalars())
        first = (
            await db.execute(
                select(func.min(func.coalesce(ContentItem.published_at, ContentItem.crawled_at))).where(
                    ContentItem.source_id == src.id
                )
            )
        ).scalar()
        topics.append(
            {
                "kind": "watch_term",
                "watch_source_id": src.id,
                "title": term,
                "content_ids": sorted(ids),
                "representative_content_id": None,
                "first_seen": first or src.created_at,
            }
        )
    return topics


async def compute_topic_signals(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    rules: dict[str, float] | None = None,
) -> dict[str, Any]:
    """计算所有话题的逐小时信号与状态，写入当天的 ``topic_trends``（signal-v2）。"""
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=WINDOW_HOURS)
    topics = await _event_topics(db, since) + await _watch_term_topics(db, since)
    observed = await _observed_hours(db, since)
    all_ids = sorted({cid for t in topics for cid in t["content_ids"]})
    facts = await _member_facts(db, all_ids, since)

    today = now.astimezone(UTC).date()
    await db.execute(
        delete(TopicTrend).where(TopicTrend.snapshot_date == today, TopicTrend.calculation_version == CALC_VERSION)
    )
    written = 0
    by_status: dict[str, int] = defaultdict(int)
    for t in topics:
        members = [facts[cid] for cid in t["content_ids"] if cid in facts]
        if not members:
            continue
        series = hourly_signal(members, observed_hours=observed, end=now, hours=WINDOW_HOURS)
        first_seen = min([m.ts for m in members] + ([_aware(t["first_seen"])] if t["first_seen"] else []))
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=UTC)
        status, info = classify_status(series, first_seen=first_seen, now=now, rules=rules)
        platforms: dict[str, int] = defaultdict(int)
        first_by_platform: dict[str, datetime] = {}
        for m in members:
            key = m.platform or "web"
            platforms[key] += 1
            ts = m.ts if m.ts.tzinfo else m.ts.replace(tzinfo=UTC)
            if key not in first_by_platform or ts < first_by_platform[key]:
                first_by_platform[key] = ts
        first_platform = min(first_by_platform, key=first_by_platform.get) if first_by_platform else None
        last_seen = max(m.ts if m.ts.tzinfo else m.ts.replace(tzinfo=UTC) for m in members)
        recent = sorted(members, key=lambda m: m.ts, reverse=True)[:5]
        db.add(
            TopicTrend(
                snapshot_date=today,
                topic_name=t["title"][:200],
                keyword=t["title"][:200] if t["kind"] == "watch_term" else None,
                content_count=len(members),
                avg_score=0.0,
                max_score=0.0,
                pick_count=0,
                top_items=[m.content_id for m in recent],
                calculation_version=CALC_VERSION,
                window_start=since,
                window_end=now,
                provenance_status="complete",
                topic_kind=t["kind"],
                event_group_id=t.get("event_group_id"),
                watch_source_id=t.get("watch_source_id"),
                representative_content_id=t.get("representative_content_id") or recent[0].content_id,
                signal_value=info["last24"],
                signal_prev=info["prev24"],
                signal_peak=info["peak24"],
                status=status,
                platform_distribution=dict(platforms),
                first_platform=first_platform,
                source_count=len({m.source_id for m in members if m.source_id}),
                series=series[-SERIES_HOURS:],
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                streak_days=info["streak_days"],
            )
        )
        written += 1
        by_status[status] += 1
    await db.flush()
    return {"topics": written, "by_status": dict(by_status)}


async def latest_status_for_events(db: AsyncSession, event_ids: list[int]) -> dict[int, str]:
    if not event_ids:
        return {}
    latest = (
        select(TopicTrend.event_group_id, func.max(TopicTrend.snapshot_date).label("d"))
        .where(TopicTrend.calculation_version == CALC_VERSION, TopicTrend.event_group_id.in_(event_ids))
        .group_by(TopicTrend.event_group_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(TopicTrend.event_group_id, TopicTrend.status)
            .join(
                latest,
                and_(TopicTrend.event_group_id == latest.c.event_group_id, TopicTrend.snapshot_date == latest.c.d),
            )
            .where(TopicTrend.calculation_version == CALC_VERSION)
        )
    ).all()
    return dict(rows)


def latest_snapshot_date(rows: list[TopicTrend]) -> date | None:
    return max((r.snapshot_date for r in rows), default=None)
