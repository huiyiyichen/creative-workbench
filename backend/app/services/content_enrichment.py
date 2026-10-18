"""采集入库时的内容补全（改造方案 3.3）：形态、平台 ID、作者、媒体信息、指标观测、归属日期。

适配器在 entry 里给出标准字段即可：
``media_type``、``platform_item_id``、``author_id``、``author_url``、``media``（dict）、
``metrics``（``{"views": 123, "likes": 4}``，只放真实取到的值）。
旧采集器的 ``_reddit_meta`` / ``_zhihu_meta`` / ``_douyin_hot_meta`` 在这里转换。
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.models.content_observation import MetricName

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
MEDIA_TYPES = {"article", "video", "image", "repo", "prompt", "post"}
_VIDEO_PLATFORMS = {"bilibili", "douyin", "youtube"}


def attributed_date_for(published_at: datetime | None, crawled_at: datetime | None) -> date | None:
    """归属日期：发布日期，缺发布时间按采集日期，按 Asia/Shanghai 取日（第 13 节 #17）。"""
    value = published_at or crawled_at
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TZ).date()


def media_type_for(entry: dict[str, Any], *, source_type: str | None, platform: str | None) -> str:
    explicit = entry.get("media_type")
    if isinstance(explicit, str) and explicit in MEDIA_TYPES:
        return explicit
    if (platform or "").lower() in _VIDEO_PLATFORMS or source_type in {"YouTube", "DouyinHot"}:
        return "video"
    if (platform or "").lower() == "xiaohongshu":
        return "image"
    if (platform or "").lower() == "github":
        return "repo"
    if source_type in {"Reddit", "X", "TwitterRSS"}:
        return "post"
    return "article"


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(str(value).replace(",", "").replace("_", "").strip())
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def metrics_from_entry(entry: dict[str, Any]) -> dict[str, float]:
    """标准化后的指标：只含真实取到的数值，缺失的不出现（不记 0）。"""
    out: dict[str, float] = {}
    raw = entry.get("metrics")
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in MetricName._value2member_map_:
                num = _num(value)
                if num is not None:
                    out[key] = num
    reddit = entry.get("_reddit_meta")
    if isinstance(reddit, dict):
        for src, dst in (("score", "score"), ("num_comments", "comments")):
            num = _num(reddit.get(src))
            if num is not None:
                out[dst] = num
    for meta_key in ("_zhihu_meta", "_douyin_hot_meta"):
        meta = entry.get(meta_key)
        if isinstance(meta, dict):
            hot = _num(meta.get("hot_score"))
            rank = _num(meta.get("rank"))
            if hot:
                out["hot"] = hot
            if rank:
                out["rank"] = rank
    return out


def legacy_metrics_record(metrics: dict[str, float]) -> dict[str, Any] | None:
    """写入旧 content_metrics 快照的字段（仍被旧页面读取）；缺失保持 None。"""
    if not metrics:
        return None
    mapping = {
        "views": metrics.get("views"),
        "likes": metrics.get("likes", metrics.get("score", metrics.get("hot"))),
        "comments": metrics.get("comments"),
        "shares": metrics.get("shares"),
        "favorites": metrics.get("favorites"),
    }
    record = {k: (int(v) if v is not None else None) for k, v in mapping.items()}
    return record if any(v is not None for v in record.values()) else None
