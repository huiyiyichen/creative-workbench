"""创作人格（月刊里的「本月你是哪种创作者」）：只按本月真实动作统计，规则判定，不调模型。

动作来源：新建项目、保存文稿版本、产出物、收进灵感库（含爆款拆解）、随笔。时间一律按北京时间。
人格按得分取最高；同分按 ARCHETYPES 的顺序。数字原样给前端，分享卡上的文案也只用这些数字。
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.library import LibraryItem, Note
from app.models.project import Project, ProjectOutput, ProjectRevision

TZ = ZoneInfo("Asia/Shanghai")
PLATFORM = {"xhs": "小红书", "douyin": "抖音", "bilibili": "B站", "zhihu": "知乎", "wechat": "公众号"}
VIDEO = {"video", "mv", "prompt_bundle"}

# key, 名字, 一句话（{n} 等占位由 _tagline 填）
ARCHETYPES: list[tuple[str, str, str]] = [
    ("hunter", "热点猎手", "别人还在刷，你已经拆完 {breakdowns} 条爆款开写了"),
    ("night", "深夜写字人", "{night_pct}% 的动作发生在晚上十点以后，灵感都是夜里来的"),
    ("multi", "多平台分身", "一份稿子，{platforms} 种腔调，哪个平台都接得住"),
    ("director", "视频导演", "这个月做了 {videos} 条视频向产出，镜头感拉满"),
    ("grass", "种草官", "{xhs} 篇小红书，分享欲是你的超能力"),
    ("longform", "长文派", "{longform} 篇长文，你相信把话说透的力量"),
    ("steady", "稳定输出机", "{days} 天都有动作，最长连续 {streak} 天，节奏感本感"),
    ("hoarder", "灵感囤积家", "收了 {library} 条灵感，只开了 {projects} 个项目，素材库就是你的安全感"),
    ("observer", "慢热观察者", "这个月动作不多，但每一步都算数"),
]


def month_range(month: str) -> tuple[datetime, datetime]:
    try:
        y, m = (int(x) for x in month.split("-"))
        start = datetime(y, m, 1, tzinfo=TZ)
    except (ValueError, TypeError) as exc:
        raise ValidationError("月份格式应为 YYYY-MM") from exc
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def longest_streak(days: set[date]) -> int:
    best = cur = 0
    prev: date | None = None
    for d in sorted(days):
        cur = cur + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, cur)
        prev = d
    return best


def scores(s: dict[str, Any]) -> dict[str, float]:
    total = max(1, s["actions"])
    return {
        "hunter": s["breakdowns"] * 3 + (2 if s["breakdowns"] >= 3 else 0),
        "night": (s["night_pct"] - 30) / 5 if s["actions"] >= 5 else 0,
        "multi": (s["platforms"] - 2) * 3 if s["platforms"] >= 3 else 0,
        "director": s["videos"] * 2.5,
        "grass": s["xhs"] * 2 if s["xhs"] >= 2 else 0,
        "longform": s["longform"] * 2 if s["longform"] >= 2 else 0,
        "steady": (s["days"] - 8) / 1.5 if s["days"] >= 10 else 0,
        "hoarder": (s["library"] / max(1, s["projects"]) - 4) if s["library"] >= 10 else 0,
        "observer": 0.5 if total < 5 else 0,
    }


def pick(s: dict[str, Any]) -> tuple[str, str, str]:
    sc = scores(s)
    best = max(ARCHETYPES, key=lambda a: (sc.get(a[0], 0), -ARCHETYPES.index(a)))
    if sc.get(best[0], 0) <= 0:
        best = ARCHETYPES[-1]
    return best[0], best[1], best[2].format(**s)


async def _times(db: AsyncSession, col, start: datetime, end: datetime, *where) -> list[datetime]:
    q = select(col).where(col >= start, col < end, *where)
    return [t for t in (await db.execute(q)).scalars().all() if t]


async def persona(db: AsyncSession, month: str | None = None) -> dict[str, Any]:
    month = month or datetime.now(UTC).astimezone(TZ).strftime("%Y-%m")
    start, end = month_range(month)
    projects = (
        (await db.execute(select(Project).where(Project.created_at >= start, Project.created_at < end))).scalars().all()
    )
    outputs = (
        await db.execute(
            select(ProjectOutput.kind, ProjectOutput.status, ProjectOutput.created_at).where(
                ProjectOutput.created_at >= start, ProjectOutput.created_at < end
            )
        )
    ).all()
    library = (
        await db.execute(
            select(LibraryItem.import_method, LibraryItem.meta, LibraryItem.created_at).where(
                LibraryItem.created_at >= start, LibraryItem.created_at < end
            )
        )
    ).all()
    revisions = await _times(db, ProjectRevision.created_at, start, end)
    notes = await _times(db, Note.created_at, start, end)

    stamps = [p.created_at for p in projects] + [o[2] for o in outputs] + [x[2] for x in library] + revisions + notes
    local = [t.astimezone(TZ) if t.tzinfo else t.replace(tzinfo=UTC).astimezone(TZ) for t in stamps]
    hours = [0] * 24
    for t in local:
        hours[t.hour] += 1
    days = {t.date() for t in local}
    kinds = Counter(o[0] for o in outputs)
    night = sum(hours[h] for h in (22, 23, 0, 1, 2, 3))
    breakdowns = sum(
        1 for m, meta, _ in library if m == "breakdown" or (isinstance(meta, dict) and meta.get("breakdown"))
    )
    stats = {
        "actions": len(local),
        "projects": len(projects),
        "outputs": len(outputs),
        "published": sum(1 for o in outputs if o[1] == "published"),
        "library": len(library),
        "breakdowns": breakdowns,
        "notes": len(notes),
        "revisions": len(revisions),
        "days": len(days),
        "streak": longest_streak(days),
        "night_pct": round(night * 100 / len(local)) if local else 0,
        "platforms": sum(1 for k in kinds if k in PLATFORM),
        "videos": sum(v for k, v in kinds.items() if k in VIDEO),
        "xhs": kinds.get("xhs", 0),
        "longform": kinds.get("zhihu", 0) + kinds.get("wechat", 0),
    }
    key, name, tagline = pick(stats)
    peak = max(range(24), key=lambda h: hours[h]) if local else None
    platform_mix = [{"kind": k, "label": PLATFORM[k], "count": v} for k, v in kinds.most_common() if k in PLATFORM]
    return {
        "month": month,
        "archetype": {"key": key, "name": name, "tagline": tagline},
        "stats": stats,
        "hours": hours,
        "peak_hour": peak,
        "platform_mix": platform_mix,
        "titles": [p.title for p in sorted(projects, key=lambda p: p.created_at, reverse=True)[:3]],
    }
