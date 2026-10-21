"""报告的长期追踪（5.4）：采集日历、空档回看、任意时间段、完整度、前后连贯、归档与搜索。

* 有采集数据的日期才生成日报；没有的在归档日历标「未采集」。
* 空档：连续 2 天以上没有成功同步；开机补采完成后自动生成一份空档回看（不调用模型），
  内容：这段时间的大事、升温过的话题、追踪词变化、错过的「值得做」、你收藏 / 关注的话题有什么后续、
  热榜缺失、一行采集概况。
* 任意时间段：手动选起止日期，结构同空档回看。
* 同一范围重新生成时 version + 1，旧版本保留。
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_event import ContentEventGroup
from app.models.daily_report import DailyReport
from app.models.dossier import PeriodReport, TopicDossier
from app.models.monthly_digest import MonthlyDigest
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun
from app.models.trend import TopicTrend
from app.models.trending import TrendingSnapshot
from app.models.weekly_digest import WeeklyDigest
from app.services.event_members import event_members_subquery
from app.services.term_match import title_matches
from app.services.topic_signals import CALC_VERSION, STATUS_LABEL

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
GAP_MIN_DAYS = 2
GAP_LOOKBACK_DAYS = 60

_em = event_members_subquery()


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=LOCAL_TZ)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def _range_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return _day_bounds(start)[0], _day_bounds(end)[1]


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def find_gaps(collected: set[date], start: date, end: date, *, min_days: int = GAP_MIN_DAYS) -> list[tuple[date, date]]:
    """``collected`` 中缺失的连续日期段（≥ min_days 天）。纯函数。"""
    gaps: list[tuple[date, date]] = []
    run: list[date] = []
    for d in _dates(start, end):
        if d in collected:
            if len(run) >= min_days:
                gaps.append((run[0], run[-1]))
            run = []
        else:
            run.append(d)
    if len(run) >= min_days:
        gaps.append((run[0], run[-1]))
    return gaps


async def collected_dates(db: AsyncSession, start: date, end: date) -> set[date]:
    """有过成功同步（不含补采的回填运行）的本地日期。"""
    lo, hi = _range_bounds(start, end)
    rows = (
        await db.execute(
            select(SourceSyncRun.finished_at).where(
                SourceSyncRun.finished_at >= lo,
                SourceSyncRun.finished_at < hi,
                SourceSyncRun.status.in_(("success", "empty")),
                SourceSyncRun.is_backfill.is_(False),
            )
        )
    ).scalars()
    return {ts.astimezone(LOCAL_TZ).date() for ts in rows if ts}


async def content_dates(db: AsyncSession, start: date, end: date) -> dict[date, int]:
    rows = (
        await db.execute(
            select(ContentItem.attributed_date, func.count())
            .where(ContentItem.attributed_date >= start, ContentItem.attributed_date <= end)
            .group_by(ContentItem.attributed_date)
        )
    ).all()
    return {d: n for d, n in rows if d}


async def has_collected_data(db: AsyncSession, d: date) -> bool:
    """日报补跑的判断：当天有采集或有归属到当天的内容。"""
    if d in await collected_dates(db, d, d):
        return True
    return bool((await content_dates(db, d, d)).get(d))


# ── 完整度 ────────────────────────────────────────────────────────


async def completeness(db: AsyncSession, start: date, end: date) -> dict[str, Any]:
    lo, hi = _range_bounds(start, end)
    pending = (
        await db.execute(
            select(func.count()).where(
                ContentItem.attributed_date >= start,
                ContentItem.attributed_date <= end,
                ContentItem.analysis_level != "full",
                ContentItem.skip_analysis.is_(False),
                or_(ContentItem.full_eligible.is_(None), ContentItem.full_eligible.is_(True)),
            )
        )
    ).scalar() or 0
    failed_rows = (
        await db.execute(
            select(Source.name)
            .join(SourceSyncRun, SourceSyncRun.source_id == Source.id)
            .where(SourceSyncRun.started_at >= lo, SourceSyncRun.started_at < hi, SourceSyncRun.status == "failed")
            .group_by(Source.name)
        )
    ).scalars()
    ok_rows = set(
        (
            await db.execute(
                select(Source.name)
                .join(SourceSyncRun, SourceSyncRun.source_id == Source.id)
                .where(
                    SourceSyncRun.started_at >= lo,
                    SourceSyncRun.started_at < hi,
                    SourceSyncRun.status.in_(("success", "empty")),
                )
                .group_by(Source.name)
            )
        ).scalars()
    )
    failed_sources = sorted(set(failed_rows) - ok_rows)
    trending_days = set(
        (
            await db.execute(
                select(TrendingSnapshot.snapshot_date).where(
                    TrendingSnapshot.snapshot_date >= start, TrendingSnapshot.snapshot_date <= end
                )
            )
        ).scalars()
    )
    collected = await collected_dates(db, start, end)
    days = _dates(start, end)
    return {
        "pending_analysis": pending,
        "failed_sources": failed_sources,
        "trending_missing_days": [d.isoformat() for d in days if d not in trending_days],
        "uncollected_days": [d.isoformat() for d in days if d not in collected],
        "computed_at": datetime.now(UTC).isoformat(),
    }


# ── 结构化内容（不调用模型） ───────────────────────────────────────


async def _big_events(db: AsyncSession, lo: datetime, hi: datetime, limit: int = 8) -> list[dict[str, Any]]:
    eff = func.coalesce(ContentItem.published_at, ContentItem.crawled_at)
    rows = (
        await db.execute(
            select(
                _em.c.event_group_id,
                func.count(func.distinct(ContentItem.id)),
                func.count(func.distinct(ContentItem.platform)),
            )
            .join(ContentItem, ContentItem.id == _em.c.content_id)
            .where(eff >= lo, eff < hi)
            .group_by(_em.c.event_group_id)
        )
    ).all()
    rows = sorted(rows, key=lambda r: (-r[2], -r[1]))[:limit]
    if not rows:
        return []
    gids = [r[0] for r in rows]
    reps = dict(
        (
            await db.execute(
                select(
                    ContentEventGroup.id,
                    func.coalesce(ContentEventGroup.representative_content_id, ContentEventGroup.canonical_content_id),
                ).where(ContentEventGroup.id.in_(gids))
            )
        ).all()
    )
    info = {
        c.id: c
        for c in (await db.execute(select(ContentItem).where(ContentItem.id.in_(reps.values())))).scalars().all()
    }
    out = []
    for gid, n, platforms in rows:
        rep = info.get(reps.get(gid))
        out.append(
            {
                "event_id": gid,
                "title": rep.title if rep else f"事件 {gid}",
                "content_id": rep.id if rep else None,
                "items": n,
                "platforms": platforms,
                "verdict": rep.verdict if rep else None,
            }
        )
    return out


async def _topics_in_range(db: AsyncSession, start: date, end: date) -> list[TopicTrend]:
    return list(
        (
            await db.execute(
                select(TopicTrend).where(
                    TopicTrend.calculation_version == CALC_VERSION,
                    TopicTrend.snapshot_date >= start,
                    TopicTrend.snapshot_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )


def _topic_moves(rows: list[TopicTrend]) -> dict[str, list[dict[str, Any]]]:
    """范围内出现过「升温 / 新出现」的话题，以及以「降温」收尾的话题。"""
    by_topic: dict[tuple, list[TopicTrend]] = defaultdict(list)
    for r in rows:
        by_topic[(r.topic_kind, r.event_group_id, r.watch_source_id)].append(r)
    rising, cooling = [], []
    for series in by_topic.values():
        series.sort(key=lambda r: r.snapshot_date)
        last = series[-1]
        view = {
            "title": last.topic_name,
            "kind": last.topic_kind,
            "event_id": last.event_group_id,
            "watch_source_id": last.watch_source_id,
            "status": last.status,
            "status_label": STATUS_LABEL.get(last.status or "", last.status),
            "platforms": last.platform_distribution or {},
            "content_id": last.representative_content_id,
        }
        if any(r.status in ("rising", "new") for r in series):
            rising.append({**view, "peak_signal": max((r.signal_value or 0) for r in series)})
        if last.status == "cooling":
            cooling.append(view)
    rising.sort(key=lambda x: -x["peak_signal"])
    return {"rising": rising[:10], "cooling": cooling[:10]}


async def _watch_terms(db: AsyncSession, start: date, end: date) -> list[dict[str, Any]]:
    span = (end - start).days + 1
    prev_start, prev_end = start - timedelta(days=span), start - timedelta(days=1)
    terms = (await db.execute(select(Source).where(Source.kind == "keyword"))).scalars().all()
    out = []
    for src in terms:
        term = (src.query or src.keyword or src.name or "").strip()
        cond = or_(ContentItem.source_id == src.id, title_matches(ContentItem.title, term))

        async def count(a: date, b: date, cond=cond) -> int:
            return (
                await db.execute(
                    select(func.count()).where(cond, ContentItem.attributed_date >= a, ContentItem.attributed_date <= b)
                )
            ).scalar() or 0

        cur, prev = await count(start, end), await count(prev_start, prev_end)
        out.append({"source_id": src.id, "term": term, "count": cur, "previous": prev, "delta": cur - prev})
    return sorted(out, key=lambda x: -x["count"])


async def _missed_worth(db: AsyncSession, start: date, end: date, limit: int = 12) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(ContentItem)
                .where(
                    ContentItem.attributed_date >= start,
                    ContentItem.attributed_date <= end,
                    ContentItem.verdict == "worth",
                    ContentItem.is_favorited.is_(False),
                )
                .order_by(ContentItem.triage_score.desc().nulls_last())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "content_id": c.id,
            "title": c.title,
            "platform": c.platform,
            "reason": (c.verdict_data or {}).get("reason"),
            "key_points": (c.verdict_data or {}).get("key_points") or [],
        }
        for c in rows
    ]


async def _followed_updates(db: AsyncSession, lo: datetime, hi: datetime) -> list[dict[str, Any]]:
    """你关注的专题 / 收藏过的事件在这段时间有什么后续（新增条目数与最新一条）。"""
    eff = func.coalesce(ContentItem.published_at, ContentItem.crawled_at)
    fav_events = set(
        (
            await db.execute(
                select(_em.c.event_group_id)
                .join(ContentItem, ContentItem.id == _em.c.content_id)
                .where(ContentItem.is_favorited.is_(True))
            )
        ).scalars()
    )
    followed = (await db.execute(select(TopicDossier).where(TopicDossier.followed.is_(True)))).scalars().all()
    targets: dict[int, str] = {d.event_group_id: d.title for d in followed if d.event_group_id}
    for gid in fav_events:
        targets.setdefault(gid, "")
    out = []
    for gid, title in targets.items():
        rows = (
            (
                await db.execute(
                    select(ContentItem)
                    .join(_em, _em.c.content_id == ContentItem.id)
                    .where(
                        _em.c.event_group_id == gid,
                        eff >= lo,
                        eff < hi,
                    )
                    .order_by(eff.desc())
                )
            )
            .scalars()
            .all()
        )
        if rows:
            out.append(
                {
                    "event_id": gid,
                    "title": title or rows[-1].title,
                    "new_items": len(rows),
                    "latest": {"content_id": rows[0].id, "title": rows[0].title, "platform": rows[0].platform},
                }
            )
    return sorted(out, key=lambda x: -x["new_items"])[:10]


async def build_sections(db: AsyncSession, start: date, end: date) -> dict[str, Any]:
    lo, hi = _range_bounds(start, end)
    per_day = await content_dates(db, start, end)
    collected = await collected_dates(db, start, end)
    days = _dates(start, end)
    moves = _topic_moves(await _topics_in_range(db, start, end))
    return {
        "big_events": await _big_events(db, lo, hi),
        "rising_topics": moves["rising"],
        "cooling_topics": moves["cooling"],
        "watch_terms": await _watch_terms(db, start, end),
        "missed_worth": await _missed_worth(db, start, end),
        "followed_updates": await _followed_updates(db, lo, hi),
        "daily_items": [{"date": d.isoformat(), "items": per_day.get(d, 0), "collected": d in collected} for d in days],
        "overview": {
            "items": sum(per_day.values()),
            "collected_days": len([d for d in days if d in collected]),
            "days": len(days),
        },
    }


def _title(kind: str, start: date, end: date) -> str:
    fmt = "%-m月%-d日"
    prefix = "空档回看" if kind == "gap" else "时间段报告"
    return f"{prefix} · {start.strftime(fmt)} – {end.strftime(fmt)}"


async def generate_period_report(db: AsyncSession, kind: str, start: date, end: date) -> PeriodReport:
    if end < start:
        raise ValueError("结束日期早于开始日期")
    if (end - start).days > 366:
        raise ValueError("时间段最长一年")
    prev = (
        await db.execute(
            select(func.max(PeriodReport.version)).where(
                PeriodReport.kind == kind,
                PeriodReport.start_date == start.isoformat(),
                PeriodReport.end_date == end.isoformat(),
            )
        )
    ).scalar()
    report = PeriodReport(
        kind=kind,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        version=(prev or 0) + 1,
        title=_title(kind, start, end),
    )
    try:
        report.sections = await build_sections(db, start, end)
        report.completeness = await completeness(db, start, end)
        report.status = "DONE"
    except Exception as exc:  # 结构化取数失败也留一条记录，界面可重试
        report.status = "ERROR"
        report.error = str(exc)[:500]
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def detect_and_generate_gap(db: AsyncSession, *, today: date | None = None) -> PeriodReport | None:
    """开机补采完成后调用：最近一段 ≥2 天的空档若还没有空档回看就生成一份。"""
    today = today or datetime.now(LOCAL_TZ).date()
    start = today - timedelta(days=GAP_LOOKBACK_DAYS)
    end = today - timedelta(days=1)
    first_run = (await db.execute(select(func.min(SourceSyncRun.finished_at)))).scalar()
    if first_run is None:
        return None
    start = max(start, first_run.astimezone(LOCAL_TZ).date())
    gaps = find_gaps(await collected_dates(db, start, end), start, end)
    if not gaps:
        return None
    gap_start, gap_end = gaps[-1]
    exists = (
        await db.execute(
            select(PeriodReport.id).where(
                PeriodReport.kind == "gap",
                PeriodReport.start_date == gap_start.isoformat(),
                PeriodReport.end_date == gap_end.isoformat(),
            )
        )
    ).first()
    if exists:
        return None
    return await generate_period_report(db, "gap", gap_start, gap_end)


def period_view(r: PeriodReport, *, full: bool = False) -> dict[str, Any]:
    out = {
        "id": r.id,
        "kind": r.kind,
        "title": r.title,
        "start_date": r.start_date,
        "end_date": r.end_date,
        "version": r.version,
        "status": r.status,
        "generated_at": r.generated_at,
        "completeness": r.completeness,
        "error": r.error,
    }
    if full:
        out["sections"] = r.sections
    return out


async def list_period_reports(db: AsyncSession, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    stmt = select(PeriodReport)
    if kind:
        stmt = stmt.where(PeriodReport.kind == kind)
    rows = (await db.execute(stmt.order_by(PeriodReport.generated_at.desc()).limit(limit))).scalars().all()
    return [period_view(r) for r in rows]


async def get_period_report(db: AsyncSession, report_id: int) -> dict[str, Any] | None:
    r = await db.get(PeriodReport, report_id)
    if r is None:
        return None
    versions = (
        await db.execute(
            select(PeriodReport.id, PeriodReport.version, PeriodReport.generated_at)
            .where(
                PeriodReport.kind == r.kind,
                PeriodReport.start_date == r.start_date,
                PeriodReport.end_date == r.end_date,
            )
            .order_by(PeriodReport.version.desc())
        )
    ).all()
    return {
        **period_view(r, full=True),
        "versions": [{"id": i, "version": v, "generated_at": g} for i, v, g in versions],
    }


# ── 归档日历与搜索 ────────────────────────────────────────────────


def _headline(report: DailyReport) -> str | None:
    """日历格子里的当天头条：选题第一条的标题，没有时用概览第一句。"""
    try:
        picks = json.loads(report.top_picks or "[]")
    except (TypeError, ValueError):
        picks = []
    if isinstance(picks, list) and picks:
        first = picks[0]
        if isinstance(first, dict):
            return first.get("title") or first.get("topic")
        return str(first)
    if report.overview:
        return report.overview.split("。")[0][:60]
    return None


async def archive_calendar(db: AsyncSession, year: int, month: int) -> dict[str, Any]:
    start = date(year, month, 1)
    end = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
    reports = (
        (
            await db.execute(
                select(DailyReport)
                .where(DailyReport.report_date >= start.isoformat(), DailyReport.report_date <= end.isoformat())
                .order_by(DailyReport.generated_at)
            )
        )
        .scalars()
        .all()
    )
    by_day: dict[str, DailyReport] = {}
    for r in reports:
        # 完整版优先于快照
        if r.report_date not in by_day or r.edition == "final" or by_day[r.report_date].edition != "final":
            by_day[r.report_date] = r
    collected = await collected_dates(db, start, end)
    items = await content_dates(db, start, end)
    today = datetime.now(LOCAL_TZ).date()
    days = []
    for d in _dates(start, end):
        r = by_day.get(d.isoformat())
        state = (
            "future"
            if d > today
            else "report"
            if r
            else "collected"
            if (d in collected or items.get(d))
            else "uncollected"
        )
        days.append(
            {
                "date": d.isoformat(),
                "state": state,
                "report_id": r.id if r else None,
                "edition": r.edition if r else None,
                "status": r.status if r else None,
                "headline": _headline(r) if r and r.status == "DONE" else None,
                "items": items.get(d, 0),
            }
        )
    weeks = (
        await db.execute(
            select(WeeklyDigest.id, WeeklyDigest.week_key, WeeklyDigest.week_label, WeeklyDigest.week_start).where(
                WeeklyDigest.week_end >= start.isoformat(), WeeklyDigest.week_start <= end.isoformat()
            )
        )
    ).all()
    month_row = (
        await db.execute(select(MonthlyDigest.id).where(MonthlyDigest.month_key == f"{year}-{month:02d}"))
    ).scalar_one_or_none()
    gaps = (
        (
            await db.execute(
                select(PeriodReport).where(
                    PeriodReport.kind == "gap",
                    PeriodReport.end_date >= start.isoformat(),
                    PeriodReport.start_date <= end.isoformat(),
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "year": year,
        "month": month,
        "days": days,
        "weeklies": [{"id": i, "key": k, "label": label, "start": s} for i, k, label, s in weeks],
        "monthly_id": month_row,
        "gaps": [period_view(g) for g in gaps],
    }


async def search_reports(db: AsyncSession, q: str, limit: int = 30) -> list[dict[str, Any]]:
    needle = f"%{q}%"
    out: list[dict[str, Any]] = []
    for r in (
        await db.execute(
            select(DailyReport)
            .where(
                or_(
                    DailyReport.overview.ilike(needle),
                    DailyReport.top_picks.ilike(needle),
                    DailyReport.trends.ilike(needle),
                    DailyReport.keywords.ilike(needle),
                    DailyReport.takeaway.ilike(needle),
                )
            )
            .order_by(DailyReport.report_date.desc())
            .limit(limit)
        )
    ).scalars():
        out.append(
            {
                "kind": "daily",
                "id": r.id,
                "key": r.report_date,
                "label": f"日报 {r.report_date}",
                "snippet": _snippet(r.overview, q),
            }
        )
    for r in (
        await db.execute(
            select(WeeklyDigest)
            .where(
                or_(
                    WeeklyDigest.overview.ilike(needle),
                    WeeklyDigest.top_picks.ilike(needle),
                    WeeklyDigest.trends.ilike(needle),
                )
            )
            .limit(limit)
        )
    ).scalars():
        out.append(
            {
                "kind": "weekly",
                "id": r.id,
                "key": r.week_key,
                "label": f"周刊 {r.week_label}",
                "snippet": _snippet(r.overview, q),
            }
        )
    for r in (
        await db.execute(select(MonthlyDigest).where(MonthlyDigest.overview.ilike(needle)).limit(limit))
    ).scalars():
        out.append(
            {
                "kind": "monthly",
                "id": r.id,
                "key": r.month_key,
                "label": f"月刊 {r.month_key}",
                "snippet": _snippet(r.overview, q),
            }
        )
    for r in (
        await db.execute(select(PeriodReport).where(cast(PeriodReport.sections, Text).ilike(needle)).limit(limit))
    ).scalars():
        out.append({"kind": r.kind, "id": r.id, "key": r.start_date, "label": r.title, "snippet": None})
    return out[:limit]


def _snippet(text: str | None, q: str, width: int = 40) -> str | None:
    if not text:
        return None
    i = text.find(q)
    if i < 0:
        return text[: width * 2]
    return ("…" if i > width else "") + text[max(0, i - width) : i + len(q) + width] + "…"


# ── 前后连贯 ──────────────────────────────────────────────────────


def _keywords(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    out = []
    for k in data if isinstance(data, list) else []:
        if isinstance(k, str):
            out.append(k)
        elif isinstance(k, dict):
            w = k.get("word") or k.get("keyword") or k.get("name") or k.get("text")
            if w:
                out.append(str(w))
    return out


def continuity(previous: list[str], current: list[str]) -> dict[str, list[str]]:
    """上期提到的话题本期有什么后续：延续 / 新出现 / 本期没再出现（降温）。纯函数。"""
    prev_set, cur_set = set(previous), set(current)
    return {
        "continued": [k for k in current if k in prev_set],
        "new": [k for k in current if k not in prev_set],
        "dropped": [k for k in previous if k not in cur_set],
    }


async def daily_continuity(db: AsyncSession, report_date: str) -> dict[str, Any] | None:
    rows = (
        (
            await db.execute(
                select(DailyReport)
                .where(DailyReport.report_date <= report_date, DailyReport.status == "DONE")
                .order_by(DailyReport.report_date.desc(), DailyReport.generated_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    cur = next((r for r in rows if r.report_date == report_date), None)
    prev = next((r for r in rows if r.report_date < report_date), None)
    if cur is None:
        return None
    result = continuity(_keywords(prev.keywords) if prev else [], _keywords(cur.keywords))
    return {"previous_date": prev.report_date if prev else None, **result}


async def stamp_completeness(db: AsyncSession, report: Any) -> None:
    """日报 / 周刊 / 月刊生成时记录数据完整度；取数失败不影响报告本身。"""
    try:
        if isinstance(report, DailyReport):
            start = end = date.fromisoformat(report.report_date)
        elif isinstance(report, WeeklyDigest):
            start, end = date.fromisoformat(report.week_start), date.fromisoformat(report.week_end)
        elif isinstance(report, MonthlyDigest):
            y, m = (int(x) for x in report.month_key.split("-"))
            start = date(y, m, 1)
            end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        else:
            return
        async with db.begin_nested():
            report.completeness = await completeness(db, start, end)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).debug("completeness not recorded", exc_info=True)
