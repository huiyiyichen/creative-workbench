"""选题结论（改造方案 4.3）：值得做 / 观察 / 跳过，加一句由事实拼成的理由。

结论由规则根据依据计算，不调用模型。依据：

| 依据 | 数据 | 缺失时 |
|---|---|---|
| 热度 | 平台原始指标与增速、上榜排名 | 「无平台指标」 |
| 时机 | 发布多久；话题状态；最先出现的平台 | 「观测不足」 |
| 同题 | 同一事件条数、覆盖平台 | 「未归并」 |
| 和你相关 | 命中追踪词；相关收藏数；你对同类内容的反馈 | — |
| 风险 | 完整分析的风险分 + 规则（敏感词） | 未分析时只有规则 |
| 内容质量（参考） | 信息密度、可操作性合成一项 | 「未分析」 |

计算明细（公式、权重、阈值）随结果返回，前端收进折叠区。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

Verdict = Literal["worth", "watch", "skip"]
VERDICT_LABEL: dict[str, str] = {"worth": "值得做", "watch": "观察", "skip": "跳过"}

PLATFORM_LABEL = {
    "bilibili": "B站",
    "youtube": "YouTube",
    "github": "GitHub",
    "hn": "HN",
    "reddit": "Reddit",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "zhihu": "知乎",
    "weibo": "微博",
}

METRIC_LABEL = {
    "views": "播放",
    "likes": "点赞",
    "stars": "Star",
    "score": "分数",
    "hot": "热度",
    "comments": "评论",
    "favorites": "收藏",
}

# 热度判断参照（达到即「热」）。与初筛 _ENGAGEMENT_REF 相比取更低的「够热」线。
HOT_REF: dict[str, float] = {
    "views": 200_000,
    "likes": 10_000,
    "stars": 500,
    "score": 300,
    "hot": 1_000_000,
    "favorites": 5_000,
    "comments": 1_000,
}

# 规则风险：出现即跳过（来源与敏感词），完整分析风险分 ≥ RISK_SKIP 也跳过
SENSITIVE_PATTERNS = [r"赌博", r"博彩", r"色情", r"约炮", r"代孕", r"枪支", r"毒品", r"翻墙教程"]
RISK_SKIP = 70.0
RISK_WARN = 50.0

DEFAULT_RULES: dict[str, float] = {
    "worth_points": 3,  # 依据得分 ≥ 此值为「值得做」
    "watch_points": 1,  # ≥ 此值为「观察」
    "stale_days": 7,  # 发布超过 N 天：最多「观察」
    "fresh_hours": 48,  # 发布 N 小时内算时机好
    "growth_ratio": 0.3,  # 主指标观测期增长 ≥30% 算升温
    "coverage_platforms": 2,  # 同一事件 ≥N 个平台
    "event_members": 3,  # 或同一事件 ≥N 条
    "quality_good": 70,  # 内容质量 ≥ 此值加一分
}


@dataclass
class VerdictFacts:
    title: str
    platform: str | None
    media_type: str | None
    published_at: datetime | None
    crawled_at: datetime | None
    metrics: dict[str, float] = field(default_factory=dict)
    # 主指标的首个观测与最新观测（同一指标），缺失为 None
    growth: tuple[str, float, float, float] | None = None  # (metric, first, last, hours)
    rank: float | None = None
    is_rss: bool = False
    # 同题
    event_id: int | None = None
    event_members: int = 0
    event_platforms: list[str] = field(default_factory=list)
    first_platform: str | None = None
    topic_status: str | None = None  # 5.3 话题状态（new / rising / steady / peak / cooling）
    # 和你相关
    keyword_hits: list[str] = field(default_factory=list)
    related_favorites: int = 0
    feedback: str | None = None  # like / not_relevant ...
    # 分析
    analysis_level: str = "none"
    quick_worth: bool | None = None
    risk_score: float | None = None
    quality: float | None = None
    risk_notes: list[str] = field(default_factory=list)
    comment_state: str = "none"


@dataclass
class VerdictResult:
    verdict: Verdict
    reason: str
    basis: dict[str, Any]
    missing: list[str]
    key_points: list[str]  # 列表上显示的两三个关键依据
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "label": VERDICT_LABEL[self.verdict],
            "reason": self.reason,
            "basis": self.basis,
            "missing": self.missing,
            "key_points": self.key_points,
            "detail": self.detail,
        }


def compact_number(value: float) -> str:
    if value >= 1e8:
        return f"{value / 1e8:.1f}亿".replace(".0亿", "亿")
    if value >= 1e4:
        return f"{value / 1e4:.1f}万".replace(".0万", "万")
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _age_hours(facts: VerdictFacts, now: datetime) -> float | None:
    ts = facts.published_at or facts.crawled_at
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return max(0.0, (now - ts).total_seconds() / 3600)


def _age_text(hours: float) -> str:
    if hours < 1:
        return "不到 1 小时"
    if hours < 48:
        return f"{int(hours)} 小时"
    return f"{int(hours // 24)} 天"


def _primary_metric(metrics: dict[str, float]) -> tuple[str, float] | None:
    for key in ("views", "stars", "score", "hot", "likes", "favorites", "comments"):
        if key in metrics and metrics[key] is not None:
            return key, float(metrics[key])
    return None


def rule_risks(title: str) -> list[str]:
    return [p for p in SENSITIVE_PATTERNS if re.search(p, title or "")]


def compute_verdict(
    facts: VerdictFacts,
    *,
    now: datetime | None = None,
    rules: dict[str, float] | None = None,
) -> VerdictResult:
    now = now or datetime.now(UTC)
    r = {**DEFAULT_RULES, **(rules or {})}
    points = 0
    reasons: list[str] = []
    key_points: list[str] = []
    missing: list[str] = []
    basis: dict[str, Any] = {}
    scored: list[dict[str, Any]] = []

    def add(name: str, pts: int, why: str) -> None:
        nonlocal points
        points += pts
        scored.append({"basis": name, "points": pts, "why": why})

    # ── 热度 ──
    heat: dict[str, Any] = {}
    primary = _primary_metric(facts.metrics)
    if primary:
        metric, value = primary
        heat["metric"] = metric
        heat["value"] = value
        label = METRIC_LABEL.get(metric, metric)
        if value >= HOT_REF.get(metric, float("inf")):
            add("heat", 1, f"{label} {compact_number(value)}")
            reasons.append(
                f"{PLATFORM_LABEL.get(facts.platform or '', facts.platform or '')}{label} {compact_number(value)}"
            )
        key_points.append(f"{label} {compact_number(value)}")
    if facts.rank is not None:
        heat["rank"] = facts.rank
        if facts.rank <= 10:
            add("heat", 1, f"上榜第 {int(facts.rank)}")
            reasons.append(f"上榜第 {int(facts.rank)}")
            key_points.append(f"榜 {int(facts.rank)}")
    if facts.growth:
        metric, first, last, hours = facts.growth
        heat["growth"] = {"metric": metric, "first": first, "last": last, "hours": round(hours, 1)}
        if first > 0 and (last - first) / first >= r["growth_ratio"]:
            add(
                "heat", 1, f"{METRIC_LABEL.get(metric, metric)}在 {_age_text(hours)}内涨 {compact_number(last - first)}"
            )
            reasons.append(f"{_age_text(hours)}内{METRIC_LABEL.get(metric, metric)}涨 {compact_number(last - first)}")
    if not primary and facts.rank is None:
        heat["state"] = "无平台指标" if facts.is_rss else "未采集平台指标"
        missing.append(heat["state"])
    basis["heat"] = heat

    # ── 时机 ──
    timing: dict[str, Any] = {}
    age = _age_hours(facts, now)
    if age is not None:
        timing["age_hours"] = round(age, 1)
        if age <= r["fresh_hours"]:
            add("timing", 1, f"发布 {_age_text(age)}")
    if facts.topic_status:
        timing["topic_status"] = facts.topic_status
        if facts.topic_status in ("new", "rising"):
            add("timing", 1, "话题" + ("新出现" if facts.topic_status == "new" else "升温"))
            key_points.append("新出现" if facts.topic_status == "new" else "升温")
        elif facts.topic_status == "cooling":
            add("timing", -1, "话题降温")
    else:
        timing["topic_status"] = None
        missing.append("话题观测不足")
    if facts.first_platform:
        timing["first_platform"] = facts.first_platform
    basis["timing"] = timing

    # ── 同题 ──
    same: dict[str, Any] = {
        "event_id": facts.event_id,
        "members": facts.event_members,
        "platforms": facts.event_platforms,
    }
    if facts.event_id:
        n_platforms = len(set(facts.event_platforms))
        if n_platforms >= r["coverage_platforms"]:
            add("same_topic", 1, f"{n_platforms} 个平台在报同一件事")
            reasons.insert(0, f"{n_platforms} 个平台在报同一件事")
            key_points.insert(0, f"{n_platforms} 平台")
        elif facts.event_members >= r["event_members"]:
            add("same_topic", 1, f"同一事件 {facts.event_members} 条")
            reasons.insert(0, f"同一事件已有 {facts.event_members} 条")
    else:
        missing.append("未归入事件")
    basis["same_topic"] = same

    # ── 和你相关 ──
    rel: dict[str, Any] = {
        "keyword_hits": facts.keyword_hits,
        "related_favorites": facts.related_favorites,
        "feedback": facts.feedback,
    }
    if facts.keyword_hits:
        add("relevance", 1, "命中追踪词「" + "、".join(facts.keyword_hits[:2]) + "」")
        reasons.append("命中追踪词「" + "、".join(facts.keyword_hits[:2]) + "」")
    if facts.related_favorites:
        add("relevance", 1, f"你收藏过 {facts.related_favorites} 条相关内容")
        reasons.append(f"你收藏过 {facts.related_favorites} 条相关内容")
    if facts.feedback in ("like", "great_pick"):
        add("relevance", 1, "你标记过有用")
    elif facts.feedback in ("not_relevant", "dislike"):
        add("relevance", -2, "你标记过不感兴趣")
    basis["relevance"] = rel

    # ── 内容质量（参考）与快速判断 ──
    if facts.quality is not None:
        basis["quality"] = round(facts.quality, 1)
        if facts.quality >= r["quality_good"]:
            add("quality", 1, f"内容质量 {int(facts.quality)}")
    else:
        basis["quality"] = None
        missing.append("未分析")
    if facts.quick_worth is True:
        add("quick", 1, "快速判断：值得完整分析")
    elif facts.quick_worth is False:
        add("quick", -1, "快速判断：不值得完整分析")
    basis["analysis_level"] = facts.analysis_level

    # ── 风险 ──
    rule_hits = rule_risks(facts.title)
    risk: dict[str, Any] = {"score": facts.risk_score, "rule_hits": rule_hits, "notes": facts.risk_notes[:3]}
    basis["risk"] = risk

    if facts.comment_state in ("none", "skipped"):
        missing.append("评论未采集")

    # ── 结论 ──
    if rule_hits or (facts.risk_score is not None and facts.risk_score >= RISK_SKIP):
        verdict: Verdict = "skip"
        reason = "风险较高：" + (
            "命中规则「" + "、".join(rule_hits) + "」" if rule_hits else f"风险分 {int(facts.risk_score or 0)}"
        )
    else:
        if points >= r["worth_points"]:
            verdict = "worth"
        elif points >= r["watch_points"]:
            verdict = "watch"
        else:
            verdict = "skip"
        if verdict == "worth" and age is not None and age > r["stale_days"] * 24:
            verdict = "watch"
            reasons.append(f"已发布 {_age_text(age)}")
        if facts.risk_score is not None and facts.risk_score >= RISK_WARN and verdict == "worth":
            verdict = "watch"
            reasons.append(f"风险分 {int(facts.risk_score)}，需留意")
        if reasons:
            reason = "；".join(dict.fromkeys(reasons))[:200]
        elif verdict == "skip":
            reason = "热度、时机、相关性都没有明显信号"
        else:
            reason = scored[0]["why"] if scored else "信号不足"

    detail = {
        "points": points,
        "scored": scored,
        "rules": r,
        "formula": f"依据得分 ≥ {int(r['worth_points'])} 值得做，≥ {int(r['watch_points'])} 观察，否则跳过；风险分 ≥ {int(RISK_SKIP)} 或命中敏感规则直接跳过",
    }
    return VerdictResult(
        verdict=verdict,
        reason=reason,
        basis=basis,
        missing=list(dict.fromkeys(missing)),
        key_points=list(dict.fromkeys(key_points))[:3],
        detail=detail,
    )
