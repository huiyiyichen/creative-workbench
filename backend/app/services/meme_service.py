"""今日梗雷达：从最近 24 小时的热榜标题和 72 小时的热门评论里，挑出正在流行的梗 / 新词，讲清意思和怎么用。

* 每天（北京时间）算一次，结果存 ``app_settings``（key=meme_radar），当天再看直接读；可手动刷新。
* 先用 breakdown_service.hot_phrases 本地粗算高频片段，再交给模型筛出真正的梗，避免模型凭空编。
* 没有材料（刚装好、还没采集）时不调模型，直接返回空和原因。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.content_observation import ContentComment
from app.models.trending import TrendingItem
from app.repositories.app_setting_repo import AppSettingRepository
from app.services.breakdown_service import hot_phrases
from app.utils.prompt_safety import sanitize_prompt_input

logger = logging.getLogger(__name__)

KEY = "meme_radar"
TZ = ZoneInfo("Asia/Shanghai")
MAX_TITLES = 80
MAX_COMMENTS = 300

SYSTEM_PROMPT = (
    "你是一个天天冲浪的内容编辑。从给你的热榜标题和热门评论里，挑出今天正在流行的梗、新词、句式（5–8 个）。"
    "只挑材料里真的出现、而且有传播性的；普通名词、人名、新闻事件本身不算梗。不确定来源就写「材料里看不出」。"
    "只返回 JSON："
    '{"memes":[{"word":"梗本身","meaning":"什么意思（20 字内）","origin":"从哪条热点 / 评论区冒出来的",'
    '"usage":"一句示范用法，能直接放进文案","fit":"适合用在什么内容里","platforms":["小红书/B站/抖音/微博 中合适的"],'
    '"heat":1}]}  heat 取 1–3，3 最火。'
)


def today_cn(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(TZ).date().isoformat()


async def _material(db: AsyncSession, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    rows = (
        (
            await db.execute(
                select(TrendingItem)
                .where(TrendingItem.fetched_at >= now - timedelta(hours=24))
                .order_by(TrendingItem.hot_value.desc())
                .limit(MAX_TITLES * 3)
            )
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    titles: list[dict[str, Any]] = []
    for r in rows:
        t = (r.title or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        titles.append({"title": t, "source": str(getattr(r.source, "value", r.source))})
        if len(titles) >= MAX_TITLES:
            break
    comments = (
        (
            await db.execute(
                select(ContentComment.text)
                .where(ContentComment.crawled_at >= now - timedelta(hours=72))
                .order_by(ContentComment.like_count.desc().nullslast())
                .limit(MAX_COMMENTS)
            )
        )
        .scalars()
        .all()
    )
    return titles, [c for c in comments if c]


def _clean(reply: Any) -> list[dict[str, Any]]:
    items = reply.get("memes") if isinstance(reply, dict) else reply
    out: list[dict[str, Any]] = []
    for m in items or []:
        if not isinstance(m, dict) or not str(m.get("word") or "").strip():
            continue
        try:
            heat = max(1, min(3, int(m.get("heat") or 1)))
        except (TypeError, ValueError):
            heat = 1
        out.append(
            {
                "word": str(m["word"]).strip()[:30],
                "meaning": str(m.get("meaning") or "").strip()[:60],
                "origin": str(m.get("origin") or "").strip()[:120],
                "usage": str(m.get("usage") or "").strip()[:120],
                "fit": str(m.get("fit") or "").strip()[:60],
                "platforms": [str(p).strip() for p in (m.get("platforms") or []) if str(p).strip()][:4],
                "heat": heat,
            }
        )
    out.sort(key=lambda m: -m["heat"])
    return out[:8]


async def _load(db: AsyncSession) -> dict[str, Any] | None:
    row = await AppSettingRepository(db).get_by_key(KEY)
    if row is None or not row.value:
        return None
    try:
        return json.loads(row.value)
    except ValueError:
        return None


async def radar(db: AsyncSession, *, refresh: bool = False, now: datetime | None = None) -> dict[str, Any]:
    from app.services.llm import call_llm_json

    now = now or datetime.now(UTC)
    day = today_cn(now)
    cached = await _load(db)
    if cached and cached.get("date") == day and not refresh:
        return cached
    titles, comments = await _material(db, now)
    if not titles and not comments:
        return {"date": day, "items": [], "reason": "最近 24 小时还没有热榜和评论，采集跑过一轮后再看", "at": None}
    phrases = hot_phrases([t["title"] for t in titles] + comments, top=30)
    user = (
        "热榜标题：\n"
        + "\n".join(f"- [{t['source']}] {sanitize_prompt_input(t['title'], max_chars=120)}" for t in titles)
        + f"\n\n热门评论（{len(comments)} 条，节选）：\n"
        + "\n".join(f"- {sanitize_prompt_input(c, max_chars=120)}" for c in comments[:150])
        + "\n\n高频片段（词，出现条数）："
        + ", ".join(f"{w}({c})" for w, c in phrases)
    )
    try:
        reply = await call_llm_json(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            temperature=0.5,
            max_tokens=1800,
            scene="meme_radar",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("meme radar llm failed: %s", str(exc)[:200])
        if cached:
            return {**cached, "stale": True}
        raise AppException("梗雷达暂时算不出来，请检查模型配置或稍后再试", 503, {"code": "model_unavailable"}) from exc
    result = {
        "date": day,
        "items": _clean(reply),
        "at": now.isoformat(),
        "basis": {"titles": len(titles), "comments": len(comments)},
    }
    await AppSettingRepository(db).upsert_setting(KEY, json.dumps(result, ensure_ascii=False), "今日梗雷达")
    await db.commit()
    return result
