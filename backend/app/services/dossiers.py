"""热点 · 升温 / 追踪词（5.2）与专题（5.5）。

升温榜读 ``topic_trends``（signal-v2）最新快照：每个话题一行，迷你曲线 + 状态 + 平台分布 + 代表内容 + 结论。

专题：
* 持续 3 天以上（streak_days ≥ 3）的事件自动成为专题；每个追踪词一个专题；
* 任何话题都可以「关注」（升温榜上的事件 → 专题并 followed）；
* 未关注、30 天没有新内容的自动专题归档，仍可搜索。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_event import ContentEventGroup
from app.models.daily_report import DailyReport
from app.models.dossier import PeriodReport, TopicDossier
from app.models.monthly_digest import MonthlyDigest
from app.models.source import Source
from app.models.trend import TopicTrend
from app.models.weekly_digest import WeeklyDigest
from app.services.discovery import item_cards, items_by_ids
from app.services.event_members import event_members_subquery
from app.services.topic_signals import CALC_VERSION, STATUS_LABEL

AUTO_STREAK_DAYS = 3
ARCHIVE_AFTER_DAYS = 30

_em = event_members_subquery()


class DossierNotFoundError(LookupError):
    pass


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


async def _latest_rows(db: AsyncSession) -> list[TopicTrend]:
    latest = (
        await db.execute(
            select(func.max(TopicTrend.snapshot_date)).where(TopicTrend.calculation_version == CALC_VERSION)
        )
    ).scalar()
    if latest is None:
        return []
    return list(
        (
            await db.execute(
                select(TopicTrend).where(
                    TopicTrend.calculation_version == CALC_VERSION, TopicTrend.snapshot_date == latest
                )
            )
        )
        .scalars()
        .all()
    )


def _row_view(row: TopicTrend) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.topic_kind,
        "title": row.topic_name,
        "event_id": row.event_group_id,
        "watch_source_id": row.watch_source_id,
        "status": row.status,
        "status_label": STATUS_LABEL.get(row.status or "", row.status),
        "signal": row.signal_value,
        "signal_prev": row.signal_prev,
        "signal_peak": row.signal_peak,
        "series": row.series or [],
        "platforms": row.platform_distribution or {},
        "first_platform": row.first_platform,
        "content_count": row.content_count,
        "source_count": row.source_count,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "streak_days": row.streak_days,
        "representative_id": row.representative_content_id,
        "computed_at": row.window_end,
    }


async def rising_board(
    db: AsyncSession, *, status: str | None = None, kind: str | None = None, limit: int = 50
) -> dict[str, Any]:
    rows = await _latest_rows(db)
    if status:
        rows = [r for r in rows if r.status == status]
    if kind:
        rows = [r for r in rows if r.topic_kind == kind]
    order = {"rising": 0, "new": 1, "peak": 2, "steady": 3, "cooling": 4, "quiet": 5}
    rows.sort(key=lambda r: (order.get(r.status or "quiet", 9), -(r.signal_value or 0)))
    rows = rows[:limit]
    reps = await items_by_ids(db, [r.representative_content_id for r in rows if r.representative_content_id])
    cards = {c["id"]: c for c in await item_cards(db, reps)}
    dossier_of = await _dossier_map(db, rows)
    counts: dict[str, int] = defaultdict(int)
    for r in await _latest_rows(db):
        counts[r.status or "quiet"] += 1
    return {
        "computed_at": rows[0].window_end if rows else None,
        "status_counts": dict(counts),
        "items": [
            {
                **_row_view(r),
                "representative": cards.get(r.representative_content_id),
                "dossier_id": dossier_of.get((r.event_group_id, r.watch_source_id)),
            }
            for r in rows
        ],
    }


async def _dossier_map(db: AsyncSession, rows: list[TopicTrend]) -> dict[tuple[int | None, int | None], int]:
    events = [r.event_group_id for r in rows if r.event_group_id]
    watches = [r.watch_source_id for r in rows if r.watch_source_id]
    if not events and not watches:
        return {}
    ds = (
        (
            await db.execute(
                select(TopicDossier).where(
                    or_(
                        TopicDossier.event_group_id.in_(events or [-1]),
                        TopicDossier.watch_source_id.in_(watches or [-1]),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    out: dict[tuple[int | None, int | None], int] = {}
    for d in ds:
        if d.event_group_id:
            out[(d.event_group_id, None)] = d.id
        if d.watch_source_id:
            out[(None, d.watch_source_id)] = d.id
    return out


async def watch_term_curves(db: AsyncSession) -> list[dict[str, Any]]:
    """追踪词页：每个追踪词一条曲线（signal-v2 的逐小时序列）+ 平台分布。"""
    rows = {r.watch_source_id: r for r in await _latest_rows(db) if r.topic_kind == "watch_term"}
    terms = (
        (await db.execute(select(Source).where(Source.kind == "keyword").order_by(Source.created_at))).scalars().all()
    )
    out = []
    for src in terms:
        row = rows.get(src.id)
        out.append(
            {
                "source_id": src.id,
                "term": src.query or src.keyword or src.name,
                "name": src.name,
                "platforms": src.platforms or [],
                "enabled": src.enabled,
                "interval_minutes": src.fetch_interval_minutes,
                "last_sync_at": src.last_sync_at,
                "trend": _row_view(row) if row else None,
            }
        )
    return out


# ── 专题 ────────────────────────────────────────────────────────


async def sync_dossiers(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """按最新趋势快照自动建 / 更新专题，并归档冷掉的自动专题。"""
    now = now or datetime.now(UTC)
    rows = await _latest_rows(db)
    existing_event = {
        d.event_group_id: d
        for d in (await db.execute(select(TopicDossier).where(TopicDossier.event_group_id.is_not(None)))).scalars()
    }
    existing_watch = {
        d.watch_source_id: d
        for d in (await db.execute(select(TopicDossier).where(TopicDossier.watch_source_id.is_not(None)))).scalars()
    }
    created = updated = 0
    for r in rows:
        if r.topic_kind == "event" and r.event_group_id:
            d = existing_event.get(r.event_group_id)
            if d is None and (r.streak_days or 0) < AUTO_STREAK_DAYS:
                continue
            if d is None:
                d = TopicDossier(
                    kind="event", title=r.topic_name or f"事件 {r.event_group_id}", event_group_id=r.event_group_id
                )
                db.add(d)
                existing_event[r.event_group_id] = d
                created += 1
        elif r.topic_kind == "watch_term" and r.watch_source_id:
            d = existing_watch.get(r.watch_source_id)
            if d is None:
                d = TopicDossier(kind="watch_term", title=r.topic_name or "追踪词", watch_source_id=r.watch_source_id)
                db.add(d)
                existing_watch[r.watch_source_id] = d
                created += 1
        else:
            continue
        d.status = r.status
        d.first_seen_at = min((_aware(x) for x in (d.first_seen_at, r.first_seen_at) if x), default=None)
        d.last_seen_at = max((_aware(x) for x in (d.last_seen_at, r.last_seen_at) if x), default=None)
        if d.archived_at and r.last_seen_at and _aware(r.last_seen_at) > _aware(d.archived_at):
            d.archived_at = None  # 又有新内容：取消归档
        updated += 1
    # 没有趋势行的追踪词也建专题（刚添加还没采到的）
    for src in (await db.execute(select(Source).where(Source.kind == "keyword"))).scalars():
        if src.id not in existing_watch:
            db.add(TopicDossier(kind="watch_term", title=src.query or src.name, watch_source_id=src.id))
            created += 1
    archived = 0
    cutoff = now - timedelta(days=ARCHIVE_AFTER_DAYS)
    for d in list(existing_event.values()):
        if not d.followed and d.archived_at is None and d.last_seen_at and _aware(d.last_seen_at) < cutoff:
            d.archived_at = now
            archived += 1
    await db.commit()
    return {"created": created, "updated": updated, "archived": archived}


async def follow_topic(
    db: AsyncSession,
    *,
    event_id: int | None = None,
    watch_source_id: int | None = None,
    title: str | None = None,
    query: str | None = None,
    followed: bool = True,
) -> TopicDossier:
    stmt = None
    if event_id:
        stmt = select(TopicDossier).where(TopicDossier.event_group_id == event_id)
    elif watch_source_id:
        stmt = select(TopicDossier).where(TopicDossier.watch_source_id == watch_source_id)
    d = (await db.execute(stmt)).scalar_one_or_none() if stmt is not None else None
    if d is None:
        if event_id:
            group = await db.get(ContentEventGroup, event_id)
            if group is None:
                raise DossierNotFoundError(f"event {event_id} not found")
            rep = await db.get(ContentItem, group.representative_content_id or group.canonical_content_id)
            d = TopicDossier(
                kind="event",
                title=title or (rep.title if rep else f"事件 {event_id}"),
                event_group_id=event_id,
                first_seen_at=group.first_occurrence_at,
                last_seen_at=group.last_occurrence_at,
            )
        elif watch_source_id:
            src = await db.get(Source, watch_source_id)
            if src is None:
                raise DossierNotFoundError(f"source {watch_source_id} not found")
            d = TopicDossier(kind="watch_term", title=title or src.query or src.name, watch_source_id=watch_source_id)
        else:
            if not (query or title):
                raise ValueError("需要事件、追踪词或关键词")
            d = TopicDossier(kind="manual", title=title or query, query=query or title)
        db.add(d)
    d.followed = followed
    if followed:
        d.archived_at = None
    await db.commit()
    await db.refresh(d)
    return d


async def set_followed(db: AsyncSession, dossier_id: int, followed: bool) -> TopicDossier:
    d = await db.get(TopicDossier, dossier_id)
    if d is None:
        raise DossierNotFoundError(f"dossier {dossier_id} not found")
    d.followed = followed
    if followed:
        d.archived_at = None
    await db.commit()
    return d


def _dossier_view(d: TopicDossier, trend: TopicTrend | None = None) -> dict[str, Any]:
    return {
        "id": d.id,
        "kind": d.kind,
        "title": d.title,
        "event_id": d.event_group_id,
        "watch_source_id": d.watch_source_id,
        "query": d.query,
        "followed": d.followed,
        "status": d.status,
        "status_label": STATUS_LABEL.get(d.status or "", d.status),
        "first_seen_at": d.first_seen_at,
        "last_seen_at": d.last_seen_at,
        "archived_at": d.archived_at,
        "series": (trend.series if trend else None) or [],
        "platforms": (trend.platform_distribution if trend else None) or {},
        "content_count": trend.content_count if trend else None,
    }


async def list_dossiers(db: AsyncSession, *, archived: bool = False, q: str | None = None) -> list[dict[str, Any]]:
    stmt = select(TopicDossier)
    stmt = stmt.where(TopicDossier.archived_at.is_not(None) if archived else TopicDossier.archived_at.is_(None))
    if q:
        stmt = stmt.where(TopicDossier.title.ilike(f"%{q}%"))
    ds = (
        (await db.execute(stmt.order_by(TopicDossier.followed.desc(), TopicDossier.last_seen_at.desc().nulls_last())))
        .scalars()
        .all()
    )
    trends = await _latest_rows(db)
    by_event = {t.event_group_id: t for t in trends if t.event_group_id}
    by_watch = {t.watch_source_id: t for t in trends if t.watch_source_id}
    return [_dossier_view(d, by_event.get(d.event_group_id) or by_watch.get(d.watch_source_id)) for d in ds]


async def _dossier_content_ids(db: AsyncSession, d: TopicDossier) -> list[int]:
    if d.event_group_id:
        return list(
            (
                await db.execute(
                    select(_em.c.content_id).where(
                        _em.c.event_group_id == d.event_group_id,
                    )
                )
            ).scalars()
        )
    term = None
    conds = []
    if d.watch_source_id:
        src = await db.get(Source, d.watch_source_id)
        term = (src.query or src.keyword or src.name) if src else None
        conds.append(ContentItem.source_id == d.watch_source_id)
    term = term or d.query
    if term:
        conds.append(ContentItem.title.ilike(f"%{term}%"))
    if not conds:
        return []
    return list((await db.execute(select(ContentItem.id).where(or_(*conds)).limit(500))).scalars())


async def _mentioning_reports(db: AsyncSession, title: str, limit: int = 12) -> list[dict[str, Any]]:
    """提到它的报告：在报告正文里按话题标题（前 12 个字）检索。"""
    needle = f"%{title[:12]}%"
    out: list[dict[str, Any]] = []
    daily = (
        await db.execute(
            select(DailyReport.id, DailyReport.report_date, DailyReport.edition)
            .where(
                or_(
                    DailyReport.overview.ilike(needle),
                    DailyReport.top_picks.ilike(needle),
                    DailyReport.trends.ilike(needle),
                )
            )
            .order_by(DailyReport.report_date.desc())
            .limit(limit)
        )
    ).all()
    out += [{"kind": "daily", "id": i, "date": d, "label": f"日报 {d}"} for i, d, _ in daily]
    weekly = (
        await db.execute(
            select(WeeklyDigest.id, WeeklyDigest.week_key, WeeklyDigest.week_label)
            .where(or_(WeeklyDigest.overview.ilike(needle), WeeklyDigest.top_picks.ilike(needle)))
            .limit(limit)
        )
    ).all()
    out += [{"kind": "weekly", "id": i, "date": k, "label": f"周刊 {label}"} for i, k, label in weekly]
    monthly = (
        await db.execute(
            select(MonthlyDigest.id, MonthlyDigest.month_key).where(MonthlyDigest.overview.ilike(needle)).limit(limit)
        )
    ).all()
    out += [{"kind": "monthly", "id": i, "date": k, "label": f"月刊 {k}"} for i, k in monthly]
    periods = (
        await db.execute(
            select(PeriodReport.id, PeriodReport.kind, PeriodReport.start_date, PeriodReport.title)
            .where(cast(PeriodReport.sections, Text).ilike(needle))
            .limit(limit)
        )
    ).all()
    out += [{"kind": k, "id": i, "date": s, "label": t} for i, k, s, t in periods]
    return out[:limit]


async def get_dossier(db: AsyncSession, dossier_id: int) -> dict[str, Any]:
    d = await db.get(TopicDossier, dossier_id)
    if d is None:
        raise DossierNotFoundError(f"dossier {dossier_id} not found")
    trends = await _latest_rows(db)
    trend = next(
        (
            t
            for t in trends
            if (d.event_group_id and t.event_group_id == d.event_group_id)
            or (d.watch_source_id and t.watch_source_id == d.watch_source_id)
        ),
        None,
    )
    ids = await _dossier_content_ids(db, d)
    items = await items_by_ids(db, ids)
    items.sort(key=lambda c: _aware(c.published_at or c.crawled_at))
    cards = await item_cards(db, items[-200:])
    first_by_platform: dict[str, datetime] = {}
    for c in items:
        ts = _aware(c.published_at or c.crawled_at)
        key = c.platform or "web"
        if key not in first_by_platform or ts < first_by_platform[key]:
            first_by_platform[key] = ts
    favorites = [c for c in cards if c["is_favorited"]]
    rep = next((c for c in cards if trend and c["id"] == trend.representative_content_id), cards[-1] if cards else None)
    return {
        **_dossier_view(d, trend),
        "timeline": cards,
        "first_by_platform": sorted(
            [{"platform": p, "at": at} for p, at in first_by_platform.items()], key=lambda x: x["at"]
        ),
        "reports": await _mentioning_reports(db, d.title),
        "favorites": favorites,
        "verdict": {"verdict": rep["verdict"], "label": rep["verdict_label"], "reason": rep["verdict_reason"]}
        if rep
        else None,
        "trend_computed_at": trend.window_end if trend else None,
    }
