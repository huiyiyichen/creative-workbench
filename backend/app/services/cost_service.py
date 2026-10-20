"""花费总览：把分析、报告、创作、阅读的 LLM 花费和生图 / 视频 / 配乐的生成花费放在一处看。

口径：
- LLM 以调用日志的 total_cost 为准（agent 运行上的 cost 是同一批调用的汇总，不重复计）；
- 生成以生成任务的 cost 为准（厂商不回报价格时为 0，界面会说明「未计价」）；
- 日期按北京时间。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cost_repo import CostRepository

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# 场景 → 用途分组
SCENE_GROUPS: dict[str, tuple[str, str]] = {}
for _scene in (
    "content_analysis",
    "content_prescreen",
    "content_enrichment",
    "quick_judge",
    "classification",
    "event_normalization",
    "comment_digest",
    "relation_discovery",
    "topic_clustering",
    "angle_recommend",
):
    SCENE_GROUPS[_scene] = ("analysis", "采集分析")
for _scene in ("daily_report", "weekly_digest", "monthly_digest"):
    SCENE_GROUPS[_scene] = ("report", "报告")
for _scene in ("reader_translate",):
    SCENE_GROUPS[_scene] = ("reading", "阅读翻译")

SCENE_LABELS = {
    "content_analysis": "完整分析",
    "content_prescreen": "初筛",
    "content_enrichment": "补充信息",
    "quick_judge": "快速判断",
    "classification": "分类",
    "event_normalization": "事件归并",
    "comment_digest": "评论摘要",
    "relation_discovery": "关联发现",
    "topic_clustering": "话题聚类",
    "angle_recommend": "角度推荐",
    "daily_report": "日报",
    "weekly_digest": "周刊",
    "monthly_digest": "月刊",
    "reader_translate": "阅读翻译",
    "studio_draft": "写稿",
    "studio_platform": "平台改写",
    "studio_suggest": "修改建议",
    "studio_animation_plan": "动画分镜",
    "image_prompt": "生图提示词",
    "distill_style": "提炼风格",
    "model_test": "模型测试",
}

GEN_LABELS = {"image": "生图", "video": "视频生成", "music": "配乐"}


def scene_group(scene: str | None) -> tuple[str, str]:
    s = scene or "general"
    if s in SCENE_GROUPS:
        return SCENE_GROUPS[s]
    if s.startswith(("studio_", "flow_")) or s in ("image_prompt", "distill_style"):
        return ("create", "创作")
    return ("other", "其他")


def scene_label(scene: str | None) -> str:
    s = scene or "general"
    if s in SCENE_LABELS:
        return SCENE_LABELS[s]
    if s.startswith("flow_"):
        return "全流程 · " + s.removeprefix("flow_")
    return s


def _as_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _r(v: float) -> float:
    return round(float(v or 0), 4)


def _top(d: dict[Any, dict], n: int) -> list[dict]:
    rows = sorted(d.values(), key=lambda r: r["cost"], reverse=True)
    for r in rows:
        r["cost"] = _r(r["cost"])
    return rows[:n]


async def cost_summary(db: AsyncSession, *, days: int = 30, now: datetime | None = None) -> dict[str, Any]:
    days = max(1, min(int(days), 180))
    now = now or datetime.now(UTC)
    today = now.astimezone(LOCAL_TZ).date()
    first = today - timedelta(days=days - 1)
    start = datetime(first.year, first.month, first.day, tzinfo=LOCAL_TZ).astimezone(UTC)
    end = now + timedelta(seconds=1)
    repo = CostRepository(db)
    llm = await repo.llm_groups(start, end)
    gen = await repo.generation_groups(start, end)

    by_day: dict[date, dict[str, float]] = {first + timedelta(days=i): defaultdict(float) for i in range(days)}
    groups: dict[str, dict] = {}
    scenes: dict[str, dict] = {}
    models: dict[str, dict] = {}
    projects: dict[int, dict] = {}
    totals = {
        "llm": 0.0,
        "generation": 0.0,
        "calls": 0,
        "jobs": 0,
        "failed": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "unpriced_jobs": 0,
    }

    for day, scene, model, project_id, cost, calls, tin, tout, failed in llm:
        day = _as_date(day)
        gkey, glabel = scene_group(scene)
        if day in by_day:
            by_day[day][gkey] += cost
        g = groups.setdefault(gkey, {"key": gkey, "label": glabel, "cost": 0.0, "count": 0})
        g["cost"] += cost
        g["count"] += calls
        sc = scenes.setdefault(
            scene or "general",
            {"key": scene or "general", "label": scene_label(scene), "group": gkey, "cost": 0.0, "count": 0},
        )
        sc["cost"] += cost
        sc["count"] += calls
        mkey = model or "未知模型"
        m = models.setdefault(
            mkey, {"key": mkey, "label": mkey, "cost": 0.0, "count": 0, "tokens_in": 0, "tokens_out": 0}
        )
        m["cost"] += cost
        m["count"] += calls
        m["tokens_in"] += int(tin)
        m["tokens_out"] += int(tout)
        if project_id:
            p = projects.setdefault(
                int(project_id), {"id": int(project_id), "title": "", "cost": 0.0, "llm": 0.0, "generation": 0.0}
            )
            p["cost"] += cost
            p["llm"] += cost
        totals["llm"] += cost
        totals["calls"] += calls
        totals["failed"] += failed
        totals["tokens_in"] += int(tin)
        totals["tokens_out"] += int(tout)

    for day, kind, service, project_id, cost, jobs, failed in gen:
        day = _as_date(day)
        gkey = f"gen_{kind or 'image'}"
        glabel = GEN_LABELS.get(kind or "image", kind or "生成")
        if day in by_day:
            by_day[day][gkey] += cost
        g = groups.setdefault(gkey, {"key": gkey, "label": glabel, "cost": 0.0, "count": 0})
        g["cost"] += cost
        g["count"] += jobs
        skey = f"{glabel} · {service or '未知服务'}"
        m = models.setdefault(
            skey, {"key": skey, "label": skey, "cost": 0.0, "count": 0, "tokens_in": 0, "tokens_out": 0}
        )
        m["cost"] += cost
        m["count"] += jobs
        if project_id:
            p = projects.setdefault(
                int(project_id), {"id": int(project_id), "title": "", "cost": 0.0, "llm": 0.0, "generation": 0.0}
            )
            p["cost"] += cost
            p["generation"] += cost
        totals["generation"] += cost
        totals["jobs"] += jobs
        totals["failed"] += failed
        if not cost:
            totals["unpriced_jobs"] += jobs

    titles = await repo.project_titles(list(projects))
    for pid, p in projects.items():
        p["title"] = titles.get(pid, f"项目 {pid}")
        p["llm"] = _r(p["llm"])
        p["generation"] = _r(p["generation"])

    series = [
        {"date": d.isoformat(), "total": _r(sum(v.values())), **{k: _r(x) for k, x in v.items()}}
        for d, v in by_day.items()
    ]
    today_total = series[-1]["total"] if series else 0.0
    prev7 = sum(s["total"] for s in series[-8:-1]) / 7 if len(series) >= 8 else None
    from app.services.analysis_funnel import budget_status

    budget = await budget_status(db)
    return {
        "days": days,
        "start": first.isoformat(),
        "end": today.isoformat(),
        "total": _r(totals["llm"] + totals["generation"]),
        "llm": _r(totals["llm"]),
        "generation": _r(totals["generation"]),
        "today": today_total,
        "avg_7d": _r(prev7) if prev7 is not None else None,
        "calls": totals["calls"],
        "jobs": totals["jobs"],
        "failed": totals["failed"],
        "unpriced_jobs": totals["unpriced_jobs"],
        "tokens_in": totals["tokens_in"],
        "tokens_out": totals["tokens_out"],
        "analysis_budget": budget,
        "series": series,
        "groups": _top(groups, 20),
        "scenes": _top(scenes, 15),
        "models": _top(models, 10),
        "projects": _top(projects, 10),
    }
