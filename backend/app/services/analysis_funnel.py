"""分析漏斗与每日预算（改造方案 4.1 / 4.2）。

采到 → 去重 → 规则预筛 → 免费初筛（入库时）→ 快速判断（初筛过线的，便宜模型，20 条一批）
→ 完整分析（快速判断过线的，受每日预算约束，按初筛分从高到低）。

* 预算：默认每天 5 元（设置 ``analysis_daily_budget``），快速判断与完整分析共用；
  到上限即停，剩余的排到次日；排队超过 3 天的不再自动分析，保留初筛分。
* 按需补分析（点开详情、收藏、用作项目来源）不受预算限制，走现有 API。
* 快速判断模型：设置 ``quick_judge_routing_group``，未设置时用 ``ANALYSIS_LITE_ROUTING_GROUP``，
  该组没有可用模型时回落到默认路由。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.content import ContentItem
from app.repositories.analysis_funnel_repo import AnalysisFunnelRepository
from app.repositories.app_setting_repo import AppSettingRepository
from app.repositories.content_repo import FUNNEL_QUEUE_DAYS

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
BUDGET_KEY = "analysis_daily_budget"
TRIAGE_THRESHOLD_KEY = "triage_threshold"
QUICK_ROUTING_KEY = "quick_judge_routing_group"
DEFAULT_BUDGET = 5.0
DEFAULT_TRIAGE_THRESHOLD = 35.0
QUICK_BATCH = 20


@dataclass
class FunnelSettings:
    daily_budget: float = DEFAULT_BUDGET
    triage_threshold: float = DEFAULT_TRIAGE_THRESHOLD
    quick_routing_group: str | None = None


async def load_funnel_settings(db: AsyncSession) -> FunnelSettings:
    repo = AppSettingRepository(db)

    async def _float(key: str, default: float) -> float:
        row = await repo.get_by_key(key)
        try:
            return float(row.value) if row and row.value not in (None, "") else default
        except ValueError:
            return default

    quick = await repo.get_by_key(QUICK_ROUTING_KEY)
    return FunnelSettings(
        daily_budget=await _float(BUDGET_KEY, DEFAULT_BUDGET),
        triage_threshold=await _float(TRIAGE_THRESHOLD_KEY, DEFAULT_TRIAGE_THRESHOLD),
        quick_routing_group=(quick.value or None) if quick else None,
    )


async def save_funnel_settings(db: AsyncSession, **values: Any) -> FunnelSettings:
    repo = AppSettingRepository(db)
    mapping = {
        "daily_budget": BUDGET_KEY,
        "triage_threshold": TRIAGE_THRESHOLD_KEY,
        "quick_routing_group": QUICK_ROUTING_KEY,
    }
    for name, key in mapping.items():
        if name in values and values[name] is not None:
            await repo.upsert_setting(key, str(values[name]))
    await db.commit()
    return await load_funnel_settings(db)


def local_day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


async def budget_status(db: AsyncSession, cfg: FunnelSettings | None = None) -> dict[str, float]:
    cfg = cfg or await load_funnel_settings(db)
    spent = await AnalysisFunnelRepository(db).spent_since(local_day_start())
    return {"budget": cfg.daily_budget, "spent": round(spent, 4), "remaining": round(cfg.daily_budget - spent, 4)}


async def budget_exhausted(db: AsyncSession, cfg: FunnelSettings | None = None) -> bool:
    status = await budget_status(db, cfg)
    return status["remaining"] <= 0


# ── 快速判断 ─────────────────────────────────────────────────────────

QUICK_SYSTEM = (
    "你是内容选题编辑。只看标题和摘要，判断每条内容是否值得做完整分析（对中文内容创作者有选题价值）。" "只输出 JSON。"
)
QUICK_USER = (
    '逐条判断下面的内容。输出 JSON：{{"items": [{{"id": 编号, "worth": true/false, '
    '"tags": ["最多 3 个中文标签"], "summary": "一句中文摘要，不超过 40 字"}}]}}\n\n{items}'
)


def build_quick_messages(items: list[ContentItem]) -> list[dict[str, str]]:
    from app.utils.prompt_safety import sanitize_prompt_input

    lines = []
    for item in items:
        summary = (item.summary or "")[:240]
        lines.append(
            json.dumps(
                {
                    "id": item.id,
                    "title": sanitize_prompt_input(item.title or "", max_chars=200),
                    "summary": sanitize_prompt_input(summary, max_chars=240),
                    "platform": item.platform,
                    "type": item.media_type,
                },
                ensure_ascii=False,
            )
        )
    return [
        {"role": "system", "content": QUICK_SYSTEM},
        {"role": "user", "content": QUICK_USER.format(items="\n".join(lines))},
    ]


def parse_quick_result(result: Any, ids: list[int]) -> dict[int, dict[str, Any]]:
    """只接受批内 id；缺项的条目视为未判断（返回里没有）。"""
    rows = result.get("items") if isinstance(result, dict) else result
    out: dict[int, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    allowed = set(ids)
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            cid = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        if cid not in allowed:
            continue
        tags = row.get("tags") if isinstance(row.get("tags"), list) else []
        out[cid] = {
            "worth": bool(row.get("worth")),
            "tags": [str(t)[:20] for t in tags[:3]],
            "summary": str(row.get("summary") or "")[:80] or None,
        }
    return out


async def _quick_routing_group(cfg: FunnelSettings) -> str:
    from app.services.llm import _model_cache

    for group in (cfg.quick_routing_group, settings.ANALYSIS_LITE_ROUTING_GROUP):
        if not group:
            continue
        try:
            if await _model_cache.get_route_models(group):
                return group
        except Exception:
            logger.debug("忽略的异常（analysis_funnel.py）", exc_info=True)
            continue
    return "default"


async def run_quick_batch(db: AsyncSession, cfg: FunnelSettings | None = None) -> dict[str, int]:
    """取一批（20 条）做快速判断，写 quick_result / full_eligible / 经历。"""
    from app.services.content_journey import record_journey
    from app.services.llm.provider import call_llm_json_with_metadata

    cfg = cfg or await load_funnel_settings(db)
    repo = AnalysisFunnelRepository(db)
    since = datetime.now(UTC) - timedelta(days=FUNNEL_QUEUE_DAYS)
    items = list(await repo.quick_candidates(threshold=cfg.triage_threshold, since=since, limit=QUICK_BATCH))
    if not items:
        return {"judged": 0, "passed": 0, "fallback": 0}

    ids = [i.id for i in items]
    parsed: dict[int, dict[str, Any]] = {}
    fallback = False
    try:
        result, _meta = await call_llm_json_with_metadata(
            build_quick_messages(items),
            temperature=0.2,
            max_tokens=1800,
            scene="quick_judge",
            routing_group=await _quick_routing_group(cfg),
        )
        parsed = parse_quick_result(result, ids)
    except Exception:
        logger.warning("quick judge failed for %d items; using triage fallback", len(ids), exc_info=True)
        fallback = True

    passed = 0
    for item in items:
        verdict = parsed.get(item.id)
        if verdict is None:
            # 模型不可用或漏判：按初筛分兜底，高于阈值 15 分的放行
            worth = (item.triage_score or 0) >= cfg.triage_threshold + 15
            verdict = {"worth": worth, "tags": [], "summary": None, "fallback": True}
        item.quick_result = verdict
        item.full_eligible = bool(verdict["worth"])
        item.analysis_level = "quick"
        passed += int(item.full_eligible)
        await record_journey(
            db,
            item.id,
            "quick",
            ("快速判断：值得完整分析" if item.full_eligible else "快速判断：不做完整分析")
            + ("（按初筛分兜底）" if verdict.get("fallback") else ""),
            detail=verdict,
        )
    await db.commit()
    return {"judged": len(items), "passed": passed, "fallback": int(fallback)}


async def prepare_full_queue(db: AsyncSession, cfg: FunnelSettings | None = None) -> dict[str, Any]:
    """完整分析之前：预算没用完时先做一批快速判断；历史无初筛分的直接放行。"""
    cfg = cfg or await load_funnel_settings(db)
    merge = await _merge_events_safe(db)
    since = datetime.now(UTC) - timedelta(days=FUNNEL_QUEUE_DAYS)
    released = await AnalysisFunnelRepository(db).mark_untriaged_eligible(since=since, limit=50)
    if released:
        await db.commit()
    if await budget_exhausted(db, cfg):
        return {"budget_exhausted": True, "released": released, "judged": 0}
    quick = await run_quick_batch(db, cfg)
    return {"budget_exhausted": False, "released": released, "merge": merge, **quick}


async def _merge_events_safe(db: AsyncSession) -> dict[str, Any]:
    """事件归并在快速判断之前（4.1）：同一事件只让代表进入分析。失败不阻断分析。"""
    try:
        from app.services.event_merge import merge_recent_events

        return await merge_recent_events(db)
    except Exception:
        logger.warning("event merge before analysis failed", exc_info=True)
        await db.rollback()
        return {"error": True}
