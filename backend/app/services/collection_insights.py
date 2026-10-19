"""采集页其余部分（3.8）：建议、覆盖（漏采）、完整度、信源价值、结构。

* 覆盖：48 小时内的事件，有热榜 / 追踪词条目但你的订阅里 0 条的，列为漏采。
* 完整度：各信源的封面、发布时间、作者、平台指标、正文完整率；发布到采集的延迟中位数。
* 信源价值：30 天产出、值得做数（分母只算已完整分析）、被收藏数、与其他信源重复率、最先报道次数、分析花费；
  收藏趋势（原评分看板）按周。
* 建议：系统给出结论和一个动作（停用、立即同步、订阅作者、加视频平台）。动作需要点一下才执行（3.9）。
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_event import ContentEventGroup
from app.models.content_observation import ContentMetricObservation
from app.models.llm_model import LlmCallLog
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun
from app.services.event_members import event_members_subquery

VALUE_DAYS = 30
COVERAGE_HOURS = 48
LOW_VALUE_MIN_ITEMS = 200
SAME_AUTHOR_FAVORITES = 3
STALE_ZERO_DAYS = 3

PLATFORM_LABEL = {
    "bilibili": "B站",
    "youtube": "YouTube",
    "github": "GitHub",
    "hn": "HN",
    "reddit": "Reddit",
    "zhihu": "知乎",
    "weibo": "微博",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
}
CHINESE_PLATFORMS = {"bilibili", "zhihu", "weibo", "douyin", "xiaohongshu"}

_em = event_members_subquery()


def _aware(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


async def _sources(db: AsyncSession) -> dict[int, Source]:
    return {s.id: s for s in (await db.execute(select(Source))).scalars().all()}


async def coverage(
    db: AsyncSession, *, now: datetime | None = None, hours: int = COVERAGE_HOURS
) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    sources = await _sources(db)
    rows = (
        await db.execute(
            select(_em.c.event_group_id, ContentItem.id, ContentItem.source_id, ContentItem.platform)
            .join(ContentItem, ContentItem.id == _em.c.content_id)
            .join(ContentEventGroup, ContentEventGroup.id == _em.c.event_group_id)
            .where(ContentEventGroup.last_occurrence_at >= since)
        )
    ).all()
    by_event: dict[int, list[tuple[int, int | None, str | None]]] = defaultdict(list)
    for gid, cid, sid, platform in rows:
        by_event[gid].append((cid, sid, platform))
    missed = []
    for gid, members in by_event.items():
        kinds = {(sources[sid].kind if sid in sources else "subscription") for _, sid, _ in members}
        if "subscription" in kinds or not kinds & {"list", "keyword"}:
            continue
        seen = sorted(
            {
                f"{PLATFORM_LABEL.get(p or '', p or '网页')}{'热榜' if sources.get(sid) and sources[sid].kind == 'list' else '搜索'}"
                for _, sid, p in members
            }
        )
        missed.append({"event_id": gid, "content_ids": [m[0] for m in members], "seen_in": seen})
    if not missed:
        return []
    reps = dict(
        (
            await db.execute(
                select(
                    ContentEventGroup.id,
                    func.coalesce(ContentEventGroup.representative_content_id, ContentEventGroup.canonical_content_id),
                ).where(ContentEventGroup.id.in_([m["event_id"] for m in missed]))
            )
        ).all()
    )
    titles = dict(
        (await db.execute(select(ContentItem.id, ContentItem.title).where(ContentItem.id.in_(reps.values())))).all()
    )
    for m in missed:
        m["content_id"] = reps.get(m["event_id"])
        m["title"] = titles.get(m["content_id"], f"事件 {m['event_id']}")
        m["text"] = f"{m['title'][:30]}：{'、'.join(m['seen_in'])}都有，你的订阅 0 条"
    return sorted(missed, key=lambda m: -len(m["content_ids"]))


async def source_completeness(
    db: AsyncSession, *, now: datetime | None = None, days: int = VALUE_DAYS
) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    items = (
        await db.execute(
            select(
                ContentItem.id,
                ContentItem.source_id,
                ContentItem.cover_url,
                ContentItem.published_at,
                ContentItem.crawled_at,
                ContentItem.author,
                func.length(func.coalesce(ContentItem.raw_content, ContentItem.summary, "")),
            ).where(ContentItem.crawled_at >= since, ContentItem.source_id.is_not(None))
        )
    ).all()
    observed = set(
        (
            await db.execute(
                select(ContentMetricObservation.content_id)
                .where(ContentMetricObservation.observed_at >= since)
                .distinct()
            )
        ).scalars()
    )
    by_source: dict[int, list] = defaultdict(list)
    for row in items:
        by_source[row[1]].append(row)
    sources = await _sources(db)
    out = []
    for sid, rows in by_source.items():
        n = len(rows)
        delays = [
            (_aware(c) - _aware(p)).total_seconds() / 3600
            for _, _, _, p, c, _, _ in rows
            if p and c and _aware(c) >= _aware(p)
        ]
        src = sources.get(sid)
        out.append(
            {
                "source_id": sid,
                "name": src.name if src else f"信源 {sid}",
                "items": n,
                "cover": _ratio(sum(1 for r in rows if r[2]), n),
                "published_at": _ratio(sum(1 for r in rows if r[3]), n),
                "author": _ratio(sum(1 for r in rows if r[5]), n),
                "metrics": _ratio(sum(1 for r in rows if r[0] in observed), n),
                "body": _ratio(sum(1 for r in rows if (r[6] or 0) >= 200), n),
                "delay_hours_median": round(statistics.median(delays), 1) if delays else None,
            }
        )
    return sorted(
        out,
        key=lambda r: min(v for v in (r["cover"], r["published_at"], r["body"]) if v is not None)
        if any(v is not None for v in (r["cover"], r["published_at"], r["body"]))
        else 1,
    )


async def source_value(db: AsyncSession, *, now: datetime | None = None, days: int = VALUE_DAYS) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    sources = await _sources(db)
    rows = (
        await db.execute(
            select(
                ContentItem.id,
                ContentItem.source_id,
                ContentItem.analysis_level,
                ContentItem.verdict,
                ContentItem.is_favorited,
                func.coalesce(ContentItem.published_at, ContentItem.crawled_at),
            ).where(ContentItem.crawled_at >= since, ContentItem.source_id.is_not(None))
        )
    ).all()
    by_source: dict[int, list] = defaultdict(list)
    source_of: dict[int, int] = {}
    for r in rows:
        by_source[r[1]].append(r)
        source_of[r[0]] = r[1]
    # 事件：重复（非代表成员）与最先报道
    members = (
        (
            await db.execute(
                select(_em.c.event_group_id, _em.c.content_id).where(_em.c.content_id.in_(list(source_of)))
            )
        ).all()
        if source_of
        else []
    )
    reps = (
        dict(
            (
                await db.execute(
                    select(
                        ContentEventGroup.id,
                        func.coalesce(
                            ContentEventGroup.representative_content_id, ContentEventGroup.canonical_content_id
                        ),
                    ).where(ContentEventGroup.id.in_({g for g, _ in members}))
                )
            ).all()
        )
        if members
        else {}
    )
    times = {r[0]: _aware(r[5]) for r in rows}
    dup: Counter[int] = Counter()
    first: Counter[int] = Counter()
    by_group: dict[int, list[int]] = defaultdict(list)
    for gid, cid in members:
        by_group[gid].append(cid)
        if reps.get(gid) != cid:
            dup[source_of[cid]] += 1
    for cids in by_group.values():
        if len(cids) >= 2:
            earliest = min(cids, key=lambda c: times.get(c) or now)
            first[source_of[earliest]] += 1
    cost_rows = (
        await db.execute(
            select(ContentItem.source_id, func.sum(LlmCallLog.total_cost))
            .join(ContentItem, ContentItem.id == LlmCallLog.content_id)
            .where(LlmCallLog.created_at >= since)
            .group_by(ContentItem.source_id)
        )
    ).all()
    cost = {sid: float(c or 0) for sid, c in cost_rows}
    out = []
    for sid, items in by_source.items():
        src = sources.get(sid)
        analyzed = [r for r in items if r[2] == "full"]
        out.append(
            {
                "source_id": sid,
                "name": src.name if src else f"信源 {sid}",
                "kind": src.kind if src else None,
                "enabled": src.enabled if src else None,
                "items": len(items),
                "analyzed": len(analyzed),
                "worth": sum(1 for r in analyzed if r[3] == "worth"),
                "worth_rate": _ratio(sum(1 for r in analyzed if r[3] == "worth"), len(analyzed)),
                "favorited": sum(1 for r in items if r[4]),
                "used_in_projects": None,  # 项目来源在阶段 4 接入
                "duplicate_rate": _ratio(dup[sid], len(items)),
                "first_reports": first[sid],
                "cost": round(cost.get(sid, 0.0), 4),
            }
        )
    out.sort(key=lambda r: (-(r["favorited"]), -(r["worth"]), -r["items"]))
    # 收藏趋势：近 8 周每周收藏数（原评分看板）
    weeks = []
    for w in range(7, -1, -1):
        end = now - timedelta(weeks=w)
        start = end - timedelta(weeks=1)
        n = (
            await db.execute(
                select(func.count()).where(
                    ContentItem.is_favorited.is_(True), ContentItem.crawled_at >= start, ContentItem.crawled_at < end
                )
            )
        ).scalar() or 0
        weeks.append({"week_end": end.date().isoformat(), "favorites": n})
    return {"days": days, "sources": out, "favorite_trend": weeks}


async def structure(db: AsyncSession, *, now: datetime | None = None, days: int = VALUE_DAYS) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    out: dict[str, Any] = {}
    for key, col in (
        ("platform", ContentItem.platform),
        ("language", ContentItem.language),
        ("media_type", ContentItem.media_type),
    ):
        rows = (await db.execute(select(col, func.count()).where(ContentItem.crawled_at >= since).group_by(col))).all()
        out[key] = sorted(
            [
                {
                    "key": k or ("web" if key == "platform" else "unknown" if key == "language" else "article"),
                    "count": n,
                }
                for k, n in rows
            ],
            key=lambda x: -x["count"],
        )
    return out


async def suggestions(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    value: dict[str, Any] | None = None,
    struct: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    value = value or await source_value(db, now=now)
    struct = struct or await structure(db, now=now)
    sources = await _sources(db)
    out: list[dict[str, Any]] = []
    for r in value["sources"]:
        if (
            r["enabled"]
            and r["kind"] != "keyword"
            and r["items"] >= LOW_VALUE_MIN_ITEMS
            and r["favorited"] == 0
            and r["worth"] == 0
        ):
            out.append(
                {
                    "kind": "disable",
                    "source_id": r["source_id"],
                    "text": f"{r['name']}：30 天 {r['items']} 条，收藏 0 → 建议停用",
                    "action": "停用",
                }
            )
    # 连续 N 天 0 条且没有报错
    since = now - timedelta(days=STALE_ZERO_DAYS)
    runs = (
        await db.execute(
            select(SourceSyncRun.source_id, SourceSyncRun.status, SourceSyncRun.new).where(
                SourceSyncRun.started_at >= since
            )
        )
    ).all()
    by_source: dict[int, list] = defaultdict(list)
    for sid, status, new in runs:
        by_source[sid].append((status, new or 0))
    for sid, rs in by_source.items():
        src = sources.get(sid)
        if not src or not src.enabled or len(rs) < 3:
            continue
        if all(s in ("success", "empty") for s, _ in rs) and sum(n for _, n in rs) == 0:
            out.append(
                {
                    "kind": "stale",
                    "source_id": sid,
                    "text": f"{src.name} 连续 {STALE_ZERO_DAYS} 天 0 条，没有报错 → 可能已失效",
                    "action": "立即同步",
                }
            )
    # 收藏集中在同一作者
    fav_rows = (
        await db.execute(
            select(
                ContentItem.author, ContentItem.author_url, ContentItem.platform, ContentItem.media_type, func.count()
            )
            .where(ContentItem.is_favorited.is_(True), ContentItem.author.is_not(None))
            .group_by(ContentItem.author, ContentItem.author_url, ContentItem.platform, ContentItem.media_type)
        )
    ).all()
    subscribed = {(s.url or "").rstrip("/") for s in sources.values()}
    for author, author_url, platform, media, n in fav_rows:
        if n >= SAME_AUTHOR_FAVORITES and author_url and author_url.rstrip("/") not in subscribed:
            noun = "视频" if media == "video" else "内容"
            out.append(
                {
                    "kind": "subscribe",
                    "author": author,
                    "author_url": author_url,
                    "platform": platform,
                    "text": f"你收藏的 {n} 条{noun}来自同一个{'UP 主' if platform == 'bilibili' else '作者'}「{author}」→ 建议订阅",
                    "action": "订阅",
                }
            )
    media = {r["key"]: r["count"] for r in struct["media_type"]}
    platforms = {r["key"] for r in struct["platform"]}
    total = sum(media.values())
    if total >= 50 and not media.get("video"):
        cn = len(platforms & CHINESE_PLATFORMS)
        out.append(
            {
                "kind": "structure",
                "text": f"视频类内容 0 条，中文平台 {cn} 个 → 结构偏了",
                "action": "添加视频信源",
            }
        )
    return out


async def build_insights(db: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    value = await source_value(db, now=now)
    struct = await structure(db, now=now)
    return {
        "suggestions": await suggestions(db, now=now, value=value, struct=struct),
        "coverage": await coverage(db, now=now),
        "completeness": await source_completeness(db, now=now),
        "value": value,
        "structure": struct,
    }


async def missed_count(db: AsyncSession, *, now: datetime | None = None) -> int:
    return len(await coverage(db, now=now))
