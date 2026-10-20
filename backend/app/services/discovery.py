"""发现：今日（5.1）与条目详情（5.6）共用的取数。

* 条目卡片 ``item_cards``：封面（本地缓存）、形态、平台、作者、时间、结论标记与关键依据、
  指标原始值 + 变化量 + 观测时间（RSS 文章为「无平台指标」）。
* 今日 ``today_feed``：统一信息流，可按形态 / 平台筛选；视图「全部」「精选」（结论为值得做，保留 7 天）。
* 今天的信号 ``today_signals``：每个平台一条轨道，条目按发布时间放置，颜色 = 形态，亮度 = 热度。
* 右侧栏：追踪词点阵（逐小时）与各平台条数、跨平台共振（主题 × 平台）、采集状态。
* 离开天数：记录上次打开今日页的时间，超过 2 天提示「你离开了 N 天」。
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.content import ContentItem
from app.models.content_event import ContentEventGroup
from app.models.content_observation import ContentMetricObservation, MediaAsset
from app.models.source import Source
from app.services.event_members import event_members_subquery
from app.services.verdict_service import verdicts_for

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
PICKS_DAYS = 7
AWAY_DAYS = 2
LAST_SEEN_KEY = "today_last_seen_at"

MEDIA_TYPES = ("article", "video", "image", "post", "prompt", "repo")
_ENGAGEMENT_REF = {
    "views": 1_000_000,
    "likes": 50_000,
    "stars": 5_000,
    "score": 1_000,
    "hot": 10_000_000,
    "favorites": 20_000,
    "comments": 5_000,
}
PRIMARY_METRICS = ("views", "stars", "score", "hot", "likes", "favorites", "comments")

_em = event_members_subquery()


def local_day_bounds(now: datetime | None = None, days_ago: int = 0) -> tuple[datetime, datetime]:
    now = (now or datetime.now(UTC)).astimezone(LOCAL_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def heat_of(metrics: dict[str, float]) -> float | None:
    """0–1 的热度（亮度）；没有平台指标返回 None。"""
    vals = []
    for key, ref in _ENGAGEMENT_REF.items():
        v = metrics.get(key)
        if v is not None and v > 0:
            vals.append(min(1.0, math.log10(1 + v) / math.log10(1 + ref)))
    if "rank" in metrics and metrics["rank"]:
        vals.append(max(0.0, (51 - metrics["rank"]) / 50))
    return round(max(vals), 3) if vals else None


def metric_view(series: dict[str, list[tuple[datetime, float]]], is_rss: bool) -> dict[str, Any]:
    """主指标：原始值、变化量（首末两次观测之差）、观测时间。"""
    for key in (*PRIMARY_METRICS, "rank"):
        rows = series.get(key) or []
        if rows:
            first_at, first = rows[0]
            last_at, last = rows[-1]
            return {
                "metric": key,
                "value": last,
                "delta": (last - first) if len(rows) >= 2 else None,
                "since": first_at if len(rows) >= 2 else None,
                "observed_at": last_at,
                "observations": len(rows),
            }
    return {"metric": None, "state": "RSS 无平台指标" if is_rss else "无平台指标"}


async def _series(db: AsyncSession, ids: list[int]) -> dict[int, dict[str, list[tuple[datetime, float]]]]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(
                ContentMetricObservation.content_id,
                ContentMetricObservation.metric,
                ContentMetricObservation.observed_at,
                ContentMetricObservation.value,
            )
            .where(ContentMetricObservation.content_id.in_(ids))
            .order_by(ContentMetricObservation.observed_at)
        )
    ).all()
    out: dict[int, dict[str, list[tuple[datetime, float]]]] = defaultdict(lambda: defaultdict(list))
    for cid, metric, at, value in rows:
        out[cid][metric].append((at, float(value)))
    return out


async def _covers(db: AsyncSession, items: list[ContentItem]) -> dict[int, tuple[int | None, str | None]]:
    asset_ids = {c.cover_asset_id for c in items if c.cover_asset_id}
    if not asset_ids:
        return {}
    rows = (
        await db.execute(
            select(MediaAsset.id, MediaAsset.status, MediaAsset.dominant_color).where(MediaAsset.id.in_(asset_ids))
        )
    ).all()
    by_id = {aid: (aid if status == "ready" else None, color) for aid, status, color in rows}
    return {c.id: by_id.get(c.cover_asset_id, (None, None)) for c in items if c.cover_asset_id}


async def _event_info(db: AsyncSession, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    rows = (await db.execute(select(_em.c.content_id, _em.c.event_group_id).where(_em.c.content_id.in_(ids)))).all()
    if not rows:
        return {}
    gids = {gid for _, gid in rows}
    counts = dict(
        (
            await db.execute(
                select(_em.c.event_group_id, func.count())
                .where(_em.c.event_group_id.in_(gids))
                .group_by(_em.c.event_group_id)
            )
        ).all()
    )
    reps = dict(
        (
            await db.execute(
                select(ContentEventGroup.id, ContentEventGroup.representative_content_id).where(
                    ContentEventGroup.id.in_(gids)
                )
            )
        ).all()
    )
    return {
        cid: {"event_id": gid, "members": counts.get(gid, 1), "representative_id": reps.get(gid)} for cid, gid in rows
    }


async def item_cards(db: AsyncSession, items: list[ContentItem]) -> list[dict[str, Any]]:
    ids = [c.id for c in items]
    series = await _series(db, ids)
    covers = await _covers(db, items)
    verdicts = await verdicts_for(db, items)
    events = await _event_info(db, ids)
    out = []
    for c in items:
        media = c.media or {}
        s = series.get(c.id, {})
        latest = {m: rows[-1][1] for m, rows in s.items() if rows}
        is_rss = str(c.source_type or "").lower() == "rss"
        asset_id, color = covers.get(c.id, (None, None))
        v = verdicts.get(c.id) or {}
        out.append(
            {
                "id": c.id,
                "title": c.title,
                "url": c.url,
                "summary": (c.quick_result or {}).get("summary") or c.summary,
                "platform": c.platform,
                "source_id": c.source_id,
                "source_name": c.source_name,
                "media_type": c.media_type or "article",
                "author": c.author,
                "published_at": c.published_at,
                "crawled_at": c.crawled_at,
                "cover_url": c.cover_url,
                "cover_asset_id": asset_id,
                "cover_color": color,
                "duration": media.get("duration"),
                "orientation": media.get("orientation"),
                "analysis_level": c.analysis_level,
                "is_favorited": c.is_favorited,
                "heat": heat_of(latest),
                "metric": metric_view(s, is_rss),
                "verdict": v.get("verdict"),
                "verdict_label": v.get("label"),
                "verdict_reason": v.get("reason"),
                "key_points": v.get("key_points") or [],
                "user_verdict": v.get("user_verdict"),
                "event": events.get(c.id),
            }
        )
    return out


def _filters(stmt, media: str | None, platform: str | None, source_id: int | None = None):
    if media:
        if media == "article":
            stmt = stmt.where(or_(ContentItem.media_type == "article", ContentItem.media_type.is_(None)))
        else:
            stmt = stmt.where(ContentItem.media_type == media)
    if platform:
        stmt = stmt.where(ContentItem.platform == platform)
    if source_id:
        stmt = stmt.where(ContentItem.source_id == source_id)
    return stmt


def _effective_time():
    return func.coalesce(ContentItem.published_at, ContentItem.crawled_at)


async def today_feed(
    db: AsyncSession,
    *,
    view: str = "all",
    media: str | None = None,
    platform: str | None = None,
    limit: int = 40,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if view == "picks":
        since = local_day_bounds(now, days_ago=PICKS_DAYS - 1)[0]
        stmt = select(ContentItem).where(ContentItem.verdict == "worth", ContentItem.crawled_at >= since)
    else:
        # 今日：今天发布 / 采到的；当天还没有就退到最近 48 小时，保证开机时不是空页
        start, _ = local_day_bounds(now)
        stmt = select(ContentItem).where(or_(ContentItem.crawled_at >= start, ContentItem.published_at >= start))
    stmt = _filters(stmt, media, platform)
    # 已有分析的按结论 → 初筛分排；排序不显示 0–100 分
    verdict_rank = case(
        (ContentItem.verdict == "worth", 0),
        (ContentItem.verdict == "watch", 1),
        (ContentItem.verdict.is_(None), 1),
        else_=2,
    )
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (
        (
            await db.execute(
                stmt.order_by(
                    verdict_rank,
                    ContentItem.triage_score.desc().nulls_last(),
                    _effective_time().desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    cards = await item_cards(db, list(rows))
    if view == "picks":
        by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for card in cards:
            ts = (card["published_at"] or card["crawled_at"]).astimezone(LOCAL_TZ)
            by_day[ts.date().isoformat()].append(card)
        days = [{"date": d, "items": by_day[d]} for d in sorted(by_day, reverse=True)]
    else:
        days = None
    return {"view": view, "total": total, "items": cards, "days": days}


def _aware(ts: datetime) -> datetime:
    """库里有的时间不带时区（按 UTC 存），统一补上，避免排序时比较报错。"""
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


SIGNAL_RANGES = {"today": None, "48h": timedelta(hours=48), "7d": timedelta(days=7)}


async def today_signals(db: AsyncSession, *, now: datetime | None = None, range_: str = "today") -> dict[str, Any]:
    """今天的信号：每个平台一条轨道，条目按发布时间放置。

    range_：today = 本地 0 点到 24 点；48h / 7d = 截至现在的滚动窗口（窗口末端就是现在）。
    """
    now = now or datetime.now(UTC)
    span = SIGNAL_RANGES.get(range_)
    if span is None:
        range_ = "today"
        start, end = local_day_bounds(now)
    else:
        start, end = now - span, now
    rows = (
        (await db.execute(select(ContentItem).where(_effective_time() >= start, _effective_time() < end).limit(3000)))
        .scalars()
        .all()
    )
    series = await _series(db, [c.id for c in rows])
    tracks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in rows:
        latest = {m: r[-1][1] for m, r in series.get(c.id, {}).items() if r}
        tracks[c.platform or "web"].append(
            {
                "id": c.id,
                "title": c.title,
                "at": _aware(c.published_at or c.crawled_at),
                "media_type": c.media_type or "article",
                "heat": heat_of(latest),
                "verdict": c.verdict,
            }
        )
    order = sorted(tracks, key=lambda p: -len(tracks[p]))
    return {
        "range": range_,
        "start": start,
        "end": end,
        "now": now,
        "tracks": [{"platform": p, "items": sorted(tracks[p], key=lambda x: x["at"])} for p in order],
    }


async def watch_term_panel(db: AsyncSession, *, now: datetime | None = None, hours: int = 24) -> list[dict[str, Any]]:
    """追踪词：逐小时点阵（近 24 小时每小时新增条数）与各平台条数。"""
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    terms = (
        (await db.execute(select(Source).where(Source.kind == "keyword").order_by(Source.created_at))).scalars().all()
    )
    out = []
    end_h = now.replace(minute=0, second=0, microsecond=0)
    for src in terms:
        term = (src.query or src.keyword or src.name or "").strip()
        rows = (
            await db.execute(
                select(ContentItem.platform, _effective_time()).where(
                    _effective_time() >= since,
                    or_(ContentItem.source_id == src.id, ContentItem.title.ilike(f"%{term}%")),
                )
            )
        ).all()
        dots = [0] * hours
        per_platform: dict[str, int] = defaultdict(int)
        for platform, ts in rows:
            ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            idx = hours - 1 - int((end_h - ts.replace(minute=0, second=0, microsecond=0)).total_seconds() // 3600)
            if 0 <= idx < hours:
                dots[idx] += 1
            per_platform[platform or "web"] += 1
        out.append(
            {
                "source_id": src.id,
                "term": term,
                "enabled": src.enabled,
                "platforms": src.platforms or [],
                "dots": dots,
                "per_platform": dict(per_platform),
                "total": len(rows),
            }
        )
    return out


async def resonance_matrix(
    db: AsyncSession, *, now: datetime | None = None, hours: int = 48, min_platforms: int = 2, limit: int = 8
) -> dict[str, Any]:
    """跨平台共振：近 48 小时覆盖 ≥2 个平台的事件 × 平台条数。"""
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(_em.c.event_group_id, ContentItem.platform, func.count())
            .join(ContentItem, ContentItem.id == _em.c.content_id)
            .join(ContentEventGroup, ContentEventGroup.id == _em.c.event_group_id)
            .where(
                ContentEventGroup.last_occurrence_at >= since,
            )
            .group_by(_em.c.event_group_id, ContentItem.platform)
        )
    ).all()
    by_event: dict[int, dict[str, int]] = defaultdict(dict)
    for gid, platform, n in rows:
        by_event[gid][platform or "web"] = n
    picked = sorted(
        (g for g, p in by_event.items() if len(p) >= min_platforms),
        key=lambda g: (-len(by_event[g]), -sum(by_event[g].values())),
    )[:limit]
    if not picked:
        return {"platforms": [], "rows": []}
    reps = dict(
        (
            await db.execute(
                select(
                    ContentEventGroup.id,
                    func.coalesce(ContentEventGroup.representative_content_id, ContentEventGroup.canonical_content_id),
                ).where(ContentEventGroup.id.in_(picked))
            )
        ).all()
    )
    titles = dict(
        (await db.execute(select(ContentItem.id, ContentItem.title).where(ContentItem.id.in_(reps.values())))).all()
    )
    platforms = sorted({p for g in picked for p in by_event[g]})
    return {
        "platforms": platforms,
        "rows": [
            {
                "event_id": g,
                "representative_id": reps.get(g),
                "title": titles.get(reps.get(g), f"事件 {g}"),
                "cells": {p: by_event[g].get(p, 0) for p in platforms},
            }
            for g in picked
        ],
    }


async def mark_today_seen(db: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    """打开今日页时调用：返回上次打开到现在离开了几天（≥2 天才提示），并更新时间。"""
    now = now or datetime.now(UTC)
    row = await db.get(AppSetting, LAST_SEEN_KEY)
    previous = None
    if row is not None and row.value:
        try:
            previous = datetime.fromisoformat(str(row.value).strip('"'))
        except ValueError:
            previous = None
    away_days = None
    if previous is not None:
        delta_days = (now.astimezone(LOCAL_TZ).date() - previous.astimezone(LOCAL_TZ).date()).days
        away_days = delta_days if delta_days >= AWAY_DAYS else None
    if row is None:
        db.add(AppSetting(key=LAST_SEEN_KEY, value=now.isoformat()))
        try:
            await db.flush()
        except IntegrityError:  # 两个标签页 / 严格模式同时打开：另一条已写入，改为更新
            await db.rollback()
            row = await db.get(AppSetting, LAST_SEEN_KEY)
            if row is not None:
                row.value = now.isoformat()
    else:
        row.value = now.isoformat()
    await db.commit()
    return {
        "previous": previous,
        "away_days": away_days,
        "gap_start": previous.astimezone(LOCAL_TZ).date().isoformat() if away_days else None,
        "gap_end": (now.astimezone(LOCAL_TZ).date() - timedelta(days=1)).isoformat() if away_days else None,
    }


async def items_by_ids(db: AsyncSession, ids: list[int]) -> list[ContentItem]:
    if not ids:
        return []
    rows = (await db.execute(select(ContentItem).where(ContentItem.id.in_(ids)))).scalars().all()
    order = {cid: i for i, cid in enumerate(ids)}
    return sorted(rows, key=lambda c: order.get(c.id, 0))


__all__ = [
    "MEDIA_TYPES",
    "item_cards",
    "items_by_ids",
    "local_day_bounds",
    "mark_today_seen",
    "resonance_matrix",
    "today_feed",
    "today_signals",
    "watch_term_panel",
]
