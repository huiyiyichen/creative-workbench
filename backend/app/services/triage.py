"""免费初筛（改造方案 4.1）：不调用模型，按信号加权合成 0–100 的初筛分。

信号（每项 0–1，缺失的信号不参与加权，而不是记 0）：

* ``engagement``：平台原始指标（播放 / 点赞 / Star / 分数 / 热度），对数归一
* ``rank``：上榜排名，越靠前越高
* ``source_value``：信源历史价值（被收藏数 / 已分析数，平滑）
* ``keyword``：命中追踪词
* ``freshness``：新鲜度，发布 6 小时内为 1，72 小时衰减到 0
* ``coverage``：同一事件覆盖的平台数（事件归并后回填）
* ``similarity``：与收藏的相似度（本地向量可用时回填）

权重放在设置（AppSetting ``triage_weights``），可调。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_WEIGHTS: dict[str, float] = {
    "engagement": 0.25,
    "rank": 0.10,
    "source_value": 0.15,
    "keyword": 0.20,
    "freshness": 0.10,
    "coverage": 0.10,
    "similarity": 0.10,
}
TRIAGE_WEIGHTS_KEY = "triage_weights"

# 各指标的「很高」参照值：达到时 engagement=1
_ENGAGEMENT_REF = {
    "views": 1_000_000,
    "likes": 50_000,
    "favorites": 20_000,
    "comments": 5_000,
    "shares": 5_000,
    "coins": 20_000,
    "stars": 5_000,
    "score": 1_000,
    "hot": 10_000_000,
}


@dataclass
class TriageContext:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    source_value: dict[int, float] = field(default_factory=dict)  # source_id -> 0..1
    keywords: list[str] = field(default_factory=list)
    now: datetime = field(default_factory=lambda: datetime.now(UTC))


def engagement_signal(metrics: dict[str, float]) -> float | None:
    best: float | None = None
    for name, ref in _ENGAGEMENT_REF.items():
        value = metrics.get(name)
        if value is None or value <= 0:
            continue
        score = min(1.0, math.log10(value + 1) / math.log10(ref + 1))
        best = score if best is None else max(best, score)
    return best


def rank_signal(metrics: dict[str, float]) -> float | None:
    rank = metrics.get("rank")
    if rank is None or rank <= 0:
        return None
    return max(0.0, 1.0 - (rank - 1) / 50)


def freshness_signal(published_at: datetime | None, now: datetime) -> float | None:
    if published_at is None:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    hours = (now - published_at).total_seconds() / 3600
    if hours <= 6:
        return 1.0
    if hours >= 72:
        return 0.0
    return round(1 - (hours - 6) / 66, 4)


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    low = text.lower()
    hits = []
    for kw in keywords:
        parts = [p for p in re.split(r"\s+", kw.lower().strip()) if p]
        if parts and all(p in low for p in parts):
            hits.append(kw)
    return hits


def combine(signals: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """缺失的信号不参与加权；全部缺失时返回 None。"""
    total_w = 0.0
    total = 0.0
    for name, value in signals.items():
        w = weights.get(name, 0.0)
        if value is None or w <= 0:
            continue
        total_w += w
        total += w * value
    if total_w == 0:
        return None
    return round(total / total_w * 100, 1)


def triage_entry(
    *,
    title: str,
    summary: str | None,
    metrics: dict[str, float],
    published_at: datetime | None,
    source_id: int | None,
    ctx: TriageContext,
    searched_keyword: str | None = None,
) -> tuple[float | None, dict[str, Any]]:
    hits = keyword_hits(f"{title} {summary or ''}", ctx.keywords)
    if searched_keyword and searched_keyword not in hits:
        hits.append(searched_keyword)  # 追踪词搜索得到的条目视为命中
    signals: dict[str, float | None] = {
        "engagement": engagement_signal(metrics),
        "rank": rank_signal(metrics),
        "source_value": ctx.source_value.get(source_id) if source_id is not None else None,
        "keyword": (1.0 if hits else 0.0) if (ctx.keywords or hits) else None,
        "freshness": freshness_signal(published_at, ctx.now),
        "coverage": None,
        "similarity": None,
    }
    score = combine(signals, ctx.weights)
    detail = {k: v for k, v in signals.items() if v is not None}
    if hits:
        detail["keyword_hits"] = hits
    return score, detail


def rescore(signals: dict[str, Any], weights: dict[str, float]) -> float | None:
    """回填 coverage / similarity 后重算。"""
    return combine({k: v for k, v in signals.items() if k in DEFAULT_WEIGHTS}, weights)


async def load_triage_context(db: AsyncSession) -> TriageContext:
    from app.repositories.triage_repo import TriageRepository

    repo = TriageRepository(db)
    weights = dict(DEFAULT_WEIGHTS)
    raw = await repo.setting(TRIAGE_WEIGHTS_KEY)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                weights.update({k: float(v) for k, v in parsed.items() if k in DEFAULT_WEIGHTS})
        except (ValueError, TypeError):
            pass
    favorites, analyzed = await repo.source_value_counts()
    source_value = {}
    for sid, analyzed_n in analyzed.items():
        # 平滑：(收藏 + 1) / (已分析 + 10)，再放大到 0..1
        source_value[sid] = round(min(1.0, (favorites.get(sid, 0) + 1) / (analyzed_n + 10) * 5), 4)
    return TriageContext(weights=weights, source_value=source_value, keywords=await repo.tracked_keywords())
