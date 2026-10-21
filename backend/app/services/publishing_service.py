"""发布排期与发布后的数据回收（review 2026-10-20b）。

- 排期：产出物 settings.schedule = {at, platform, note, notified}；到点还没发布就推一条站内通知；
- 日历：一段时间里排了期的和已发布的产出物；
- 数据回收：已发布的产出物按发布链接回抓平台指标（播放 / 点赞 / 评论 / 收藏 / 转发……），越新抓得越勤：
  发布 2 天内每 3 小时，14 天内每 12 小时，90 天内每 3 天，之后不再抓；
- 效果：按产出形态、发布平台汇总最近一次指标的中位数，看哪类作品效果好。
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.project import Project, ProjectOutput, WorkMetricObservation

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

KIND_LABEL = {
    "xhs": "小红书",
    "zhihu": "知乎",
    "wechat": "公众号",
    "bilibili": "B站",
    "douyin": "抖音",
    "video": "讲解视频",
    "mv": "MV",
    "prompt_bundle": "提示词包",
}
PLATFORM_LABEL = {
    "bilibili": "B站",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "youtube": "YouTube",
    "github": "GitHub",
    "hn": "Hacker News",
    "reddit": "Reddit",
    "web": "网页",
}
HEADLINE_METRICS = ("views", "likes", "comments", "favorites", "shares")

FetchEntry = Callable[[AsyncSession, str], Awaitable[dict[str, Any] | None]]


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_at(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _aware(value)
    try:
        return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def platform_of(url: str | None) -> str | None:
    if not url:
        return None
    from app.services.library import parse_link

    return parse_link(url)[0]


# ── 排期 ────────────────────────────────────────────────────────────


async def _output(db: AsyncSession, output_id: int) -> ProjectOutput:
    out = await db.get(ProjectOutput, output_id)
    if out is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("产出物不存在")
    return out


async def set_schedule(
    db: AsyncSession, output_id: int, *, at: datetime | None, platform: str | None = None, note: str = ""
) -> dict[str, Any]:
    out = await _output(db, output_id)
    settings = dict(out.settings or {})
    if at is None:
        settings.pop("schedule", None)
    else:
        at = _aware(at)
        if out.status == "published":
            raise ValidationError("已经发布了，不需要再排期")
        settings["schedule"] = {
            "at": at.isoformat(),
            "platform": platform or None,
            "note": note.strip()[:200],
            "notified": False,
        }
    out.settings = settings
    await db.commit()
    return {"id": out.id, "schedule": settings.get("schedule")}


def _metrics_latest(out: ProjectOutput) -> dict[str, float]:
    return dict(((out.settings or {}).get("metrics") or {}).get("latest") or {})


def _calendar_row(out: ProjectOutput, project: Project | None) -> dict[str, Any]:
    sched = (out.settings or {}).get("schedule") or {}
    return {
        "id": out.id,
        "project_id": out.project_id,
        "project_title": project.title if project else "",
        "kind": out.kind,
        "kind_label": KIND_LABEL.get(out.kind, out.kind),
        "title": out.title or (project.title if project else ""),
        "status": out.status,
        "scheduled_at": sched.get("at"),
        "schedule_platform": sched.get("platform"),
        "schedule_note": sched.get("note") or "",
        "published_at": _aware(out.published_at).isoformat() if out.published_at else None,
        "published_url": out.published_url,
        "platform": platform_of(out.published_url) or sched.get("platform"),
        "metrics": _metrics_latest(out),
    }


async def calendar(db: AsyncSession, start: datetime, end: datetime) -> dict[str, Any]:
    """[start, end) 内排了期或已发布的产出物，按时间排序；另给出没排期的「待发布」（已完成未发布）。"""
    start, end = _aware(start), _aware(end)
    rows = (
        await db.execute(select(ProjectOutput, Project).join(Project, Project.id == ProjectOutput.project_id))
    ).all()
    items: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    for out, project in rows:
        sched_at = _parse_at(((out.settings or {}).get("schedule") or {}).get("at"))
        pub = _aware(out.published_at)
        when = pub if out.status == "published" and pub else sched_at
        if when and start <= when < end:
            items.append({**_calendar_row(out, project), "at": when.isoformat()})
        elif not sched_at and out.status in ("done", "exported") and not out.published_url:
            backlog.append(_calendar_row(out, project))
    items.sort(key=lambda r: r["at"])
    backlog.sort(key=lambda r: r["id"], reverse=True)
    return {"start": start.isoformat(), "end": end.isoformat(), "items": items, "backlog": backlog[:30]}


async def remind_due(db: AsyncSession, now: datetime | None = None) -> int:
    """到点没发布的排期推一条通知（每个排期只推一次）。"""
    from app.services.notification_service import push_notification

    now = now or _now()
    outs = (await db.execute(select(ProjectOutput).where(ProjectOutput.status != "published"))).scalars().all()
    sent = 0
    for out in outs:
        sched = dict((out.settings or {}).get("schedule") or {})
        at = _parse_at(sched.get("at"))
        if not at or sched.get("notified") or at > now:
            continue
        where = PLATFORM_LABEL.get(sched.get("platform") or "", sched.get("platform") or "")
        await push_notification(
            "info",
            "publish",
            "该发布了",
            f"「{out.title or KIND_LABEL.get(out.kind, out.kind)}」排在 {at.astimezone(LOCAL_TZ).strftime('%m-%d %H:%M')}"
            + (f" 发到{where}" if where else "")
            + "。发完把链接填回来，之后会自动回收数据。",
        )
        sched["notified"] = True
        out.settings = {**(out.settings or {}), "schedule": sched}
        sent += 1
    if sent:
        await db.commit()
    return sent


# ── 数据回收 ─────────────────────────────────────────────────────────


async def default_fetch_entry(db: AsyncSession, url: str) -> dict[str, Any] | None:
    from app.services.library import fetch_link_meta, parse_link
    from app.services.platform_keys import get_platform_keys

    platform, item_id = parse_link(url)
    if not item_id:
        return None
    return await fetch_link_meta(url, platform, item_id, api_keys=await get_platform_keys(db))


def next_check(published_at: datetime | None, checked_at: datetime | None) -> datetime | None:
    """下一次该回抓的时间；超过 90 天返回 None（不再抓）。"""
    pub = _aware(published_at)
    if pub is None:
        return None
    last = _aware(checked_at)
    if last is None:
        return pub
    age = last - pub
    if age > timedelta(days=90):
        return None
    step = (
        timedelta(hours=3)
        if age < timedelta(days=2)
        else timedelta(hours=12)
        if age < timedelta(days=14)
        else timedelta(days=3)
    )
    return last + step


async def refresh_metrics(
    db: AsyncSession, output_id: int, *, fetch: FetchEntry | None = None, now: datetime | None = None
) -> dict[str, Any]:
    out = await _output(db, output_id)
    if not out.published_url:
        raise ValidationError("还没有发布链接，填上链接后才能回收数据")
    fetch = fetch or default_fetch_entry
    now = now or _now()
    state = dict((out.settings or {}).get("metrics") or {})
    try:
        entry = await fetch(db, out.published_url)
    except Exception as exc:  # noqa: BLE001 — 平台各种失败都只记下原因，下一轮再试
        logger.info("work metrics fetch failed for output %s: %s", output_id, exc)
        entry, state["error"] = None, str(exc)[:200]
    metrics = {
        k: float(v) for k, v in ((entry or {}).get("metrics") or {}).items() if isinstance(v, int | float) and v >= 0
    }
    if metrics:
        db.add_all(
            [WorkMetricObservation(output_id=out.id, metric=k, value=v, observed_at=now) for k, v in metrics.items()]
        )
        state["latest"] = metrics
        state.pop("error", None)
    elif entry is not None:
        state["error"] = "这个平台的链接读不到公开数据"
    elif "error" not in state:
        state["error"] = "暂不支持这个链接的数据回收"
    state["checked_at"] = now.isoformat()
    out.settings = {**(out.settings or {}), "metrics": state}
    await db.commit()
    return {"id": out.id, "metrics": state}


async def refresh_due(
    db: AsyncSession, *, now: datetime | None = None, fetch: FetchEntry | None = None, limit: int = 20
) -> int:
    now = now or _now()
    outs = (
        (
            await db.execute(
                select(ProjectOutput).where(
                    ProjectOutput.published_url.is_not(None), ProjectOutput.status == "published"
                )
            )
        )
        .scalars()
        .all()
    )
    due = []
    for out in outs:
        checked = _parse_at(((out.settings or {}).get("metrics") or {}).get("checked_at"))
        nxt = next_check(out.published_at, checked)
        if nxt is not None and nxt <= now:
            due.append((nxt, out.id))
    due.sort()
    for _, oid in due[:limit]:
        await refresh_metrics(db, oid, fetch=fetch, now=now)
    return min(len(due), limit)


async def metric_series(db: AsyncSession, output_id: int) -> dict[str, list[dict[str, Any]]]:
    rows = (
        (
            await db.execute(
                select(WorkMetricObservation)
                .where(WorkMetricObservation.output_id == output_id)
                .order_by(WorkMetricObservation.observed_at)
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        out[r.metric].append({"at": _aware(r.observed_at).isoformat(), "value": r.value})
    return dict(out)


async def performance(db: AsyncSession) -> dict[str, Any]:
    """按产出形态、发布平台汇总已发布作品最近一次指标的中位数，并列出表现最好的几件。"""
    rows = (
        await db.execute(
            select(ProjectOutput, Project)
            .join(Project, Project.id == ProjectOutput.project_id)
            .where(ProjectOutput.status == "published")
        )
    ).all()
    by_kind: dict[str, list[dict[str, float]]] = defaultdict(list)
    by_platform: dict[str, list[dict[str, float]]] = defaultdict(list)
    tops: list[dict[str, Any]] = []
    tracked = 0
    for out, project in rows:
        latest = _metrics_latest(out)
        if not latest:
            continue
        tracked += 1
        by_kind[out.kind].append(latest)
        by_platform[platform_of(out.published_url) or "web"].append(latest)
        tops.append(_calendar_row(out, project))

    def summarize(groups: dict[str, list[dict[str, float]]], labels: dict[str, str]) -> list[dict[str, Any]]:
        res = []
        for key, lst in groups.items():
            med = {
                m: statistics.median(v[m] for v in lst if m in v) for m in HEADLINE_METRICS if any(m in v for v in lst)
            }
            res.append({"key": key, "label": labels.get(key, key), "count": len(lst), "median": med})
        res.sort(key=lambda r: (r["median"].get("views", 0), r["count"]), reverse=True)
        return res

    tops.sort(key=lambda r: (r["metrics"].get("views", 0), r["metrics"].get("likes", 0)), reverse=True)
    return {
        "published": len(rows),
        "tracked": tracked,
        "by_kind": summarize(by_kind, KIND_LABEL),
        "by_platform": summarize(by_platform, PLATFORM_LABEL),
        "top": tops[:5],
    }
