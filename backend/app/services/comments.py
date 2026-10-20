"""条目评论（改造方案 3.5）。

评论是单个条目的附属资料：不进信息流、不单独成页、不参与排序。
* 范围：热门前 20 条，不取回复；只存昵称与文本（不存头像、主页）。
* 触发：收藏（含收进灵感库）、被项目用作来源、在条目详情点「加载评论」。
* 刷新：收藏和项目来源的评论在采集后 24 小时刷新一次，之后不再刷新。
* 保留：未收藏内容的评论保留 30 天。
* 摘要：「总结评论」时由模型生成几条要点，每条附原评论 id，存 ``content_items.comment_digest``。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_observation import ContentComment
from app.models.library import LibraryItem
from app.services.platforms import ADAPTERS, COMMENTS, Comment, NotSupported, PlatformError, get_adapter

logger = logging.getLogger(__name__)

LIMIT = 20
REFRESH_AFTER = timedelta(hours=24)
RETENTION = timedelta(days=30)

# 采集侧 platform 字段的别名 → 适配器名
PLATFORM_ALIAS = {
    "bilibili": "bilibili",
    "b站": "bilibili",
    "youtube": "youtube",
    "hn": "hn",
    "hackernews": "hn",
    "hacker news": "hn",
    "reddit": "reddit",
}

# 评论来源（3.5）：B站、YouTube、HN、Reddit；抖音 / 小红书在阶段 4
COMMENT_PLATFORMS = frozenset(PLATFORM_ALIAS.values())

STATE_NONE = "none"
STATE_COLLECTED = "collected"
STATE_UNAVAILABLE = "unavailable"  # 无评论来源
STATE_FAILED = "failed"


class CommentError(Exception):
    pass


def _aware(ts: datetime | None) -> datetime | None:
    if ts is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


def resolve_source(item: ContentItem) -> tuple[str, str] | None:
    """(适配器名, 平台内 id)；没有评论来源返回 None。"""
    from app.services.library import parse_link

    platform = PLATFORM_ALIAS.get((item.platform or "").strip().lower())
    pid = item.platform_item_id
    if not platform or not pid:
        # 采集时没写平台 id 的老数据：从链接里认
        for url in (item.url, (item.media or {}).get("discussion_url") if isinstance(item.media, dict) else None):
            if not url:
                continue
            p, i = parse_link(url)
            if p in COMMENT_PLATFORMS and i:
                platform, pid = p, i
                break
    if (
        not platform
        or not pid
        or platform not in COMMENT_PLATFORMS
        or platform not in ADAPTERS
        or COMMENTS not in ADAPTERS[platform].capabilities
    ):
        return None
    return platform, str(pid)


def comment_key(platform: str, c: Comment) -> str:
    if c.id:
        return str(c.id)[:64]
    raw = f"{platform}|{c.author or ''}|{(c.text or '')[:300]}"
    return "h" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:40]


async def _fetch(db: AsyncSession, platform: str, pid: str) -> list[Comment]:
    from app.services.platform_keys import get_platform_keys

    keys = await get_platform_keys(db)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        adapter = get_adapter(platform, client, api_key=keys.get(platform))
        return await adapter.fetch_comments(pid, limit=LIMIT)


async def collect(db: AsyncSession, content_id: int, *, force: bool = False) -> dict[str, Any]:
    """采集（或刷新）一条内容的热门评论。force=False 时已采集的不重复采。"""
    item = await db.get(ContentItem, content_id)
    if item is None:
        raise CommentError("内容不存在")
    if not force and item.comment_state == STATE_COLLECTED:
        return await list_comments(db, content_id)
    src = resolve_source(item)
    now = datetime.now(UTC)
    if src is None:
        item.comment_state = STATE_UNAVAILABLE
        item.comment_crawled_at = now
        await db.commit()
        return await list_comments(db, content_id)
    platform, pid = src
    try:
        fetched = await _fetch(db, platform, pid)
    except NotSupported:
        item.comment_state = STATE_UNAVAILABLE
        item.comment_crawled_at = now
        await db.commit()
        return await list_comments(db, content_id)
    except (PlatformError, httpx.HTTPError, ValueError) as exc:
        item.comment_state = STATE_FAILED
        item.comment_crawled_at = now
        await db.commit()
        out = await list_comments(db, content_id)
        out["error"] = str(exc) or exc.__class__.__name__
        return out

    existing = {
        c.platform_comment_id: c
        for c in (await db.execute(select(ContentComment).where(ContentComment.content_id == content_id))).scalars()
    }
    for c in fetched[:LIMIT]:
        text = (c.text or "").strip()
        if not text:
            continue
        key = comment_key(platform, c)
        row = existing.get(key)
        if row is None:
            row = (
                await db.execute(
                    select(ContentComment).where(
                        ContentComment.platform == platform, ContentComment.platform_comment_id == key
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            db.add(
                ContentComment(
                    content_id=content_id,
                    platform=platform,
                    platform_comment_id=key,
                    author_name=(c.author or "")[:120] or None,
                    text=text,
                    like_count=c.likes,
                    reply_count=c.replies,
                    published_at=c.published_at,
                    crawled_at=now,
                )
            )
        else:  # 重复采集只更新点赞与回复数
            row.like_count = c.likes
            row.reply_count = c.replies  # crawled_at 保留首次采集时间（刷新一次、保留期都按它算）
    item.comment_state = STATE_COLLECTED
    item.comment_crawled_at = now
    await db.commit()
    return await list_comments(db, content_id)


def comment_view(c: ContentComment) -> dict[str, Any]:
    return {
        "id": c.id,
        "author": c.author_name,
        "text": c.text,
        "likes": c.like_count,
        "replies": c.reply_count,
        "published_at": c.published_at,
    }


async def list_comments(db: AsyncSession, content_id: int) -> dict[str, Any]:
    item = await db.get(ContentItem, content_id)
    if item is None:
        raise CommentError("内容不存在")
    rows = (
        (
            await db.execute(
                select(ContentComment)
                .where(ContentComment.content_id == content_id)
                .order_by(ContentComment.like_count.desc().nulls_last(), ContentComment.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "state": item.comment_state,
        "crawled_at": item.comment_crawled_at,
        "source": (resolve_source(item) or (None,))[0],
        "items": [comment_view(c) for c in rows],
        "digest": item.comment_digest,
    }


def _digest_messages(title: str, rows: list[ContentComment]) -> list[dict[str, str]]:
    lines = "\n".join(f"[{c.id}] ({c.like_count or 0} 赞) {c.text[:300]}" for c in rows)
    return [
        {
            "role": "system",
            "content": (
                "你在帮内容创作者读一条内容下面的热门评论。归纳 3 到 5 条要点：观众在争论什么、"
                "补充了什么信息、有哪些疑问或槽点。每条要点必须列出支撑它的评论 id。"
                '只输出 JSON：{"points": [{"text": "要点", "comment_ids": [1, 2]}]}'
            ),
        },
        {"role": "user", "content": f"内容标题：{title}\n\n评论（方括号里是 id）：\n{lines}"},
    ]


async def digest(db: AsyncSession, content_id: int) -> dict[str, Any]:
    from app.services.llm import provider

    item = await db.get(ContentItem, content_id)
    if item is None:
        raise CommentError("内容不存在")
    rows = (
        (
            await db.execute(
                select(ContentComment)
                .where(ContentComment.content_id == content_id)
                .order_by(ContentComment.like_count.desc().nulls_last())
                .limit(LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise CommentError("还没有评论可以总结")
    result = await provider.call_llm_json(
        _digest_messages(item.title or "", rows), temperature=0.2, max_tokens=1200, scene="comment_digest"
    )
    valid = {c.id for c in rows}
    points = []
    for p in (result.get("points") if isinstance(result, dict) else None) or []:
        if not isinstance(p, dict) or not str(p.get("text") or "").strip():
            continue
        ids = [int(i) for i in p.get("comment_ids") or [] if str(i).isdigit() and int(i) in valid]
        points.append({"text": str(p["text"]).strip(), "comment_ids": ids})
    if not points:
        raise CommentError("模型没有给出可用的要点")
    item.comment_digest = {
        "points": points[:5],
        "based_on": len(rows),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    await db.commit()
    return item.comment_digest


async def on_kept(db: AsyncSession, content_id: int) -> None:
    """收藏 / 用作项目来源：没采过就采一次（失败不影响收藏本身）。"""
    try:
        await collect(db, content_id)
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.info("comment collect after keep failed for %s", content_id, exc_info=True)


async def _kept_content_ids(db: AsyncSession) -> set[int]:
    lib = set(
        (
            await db.execute(
                select(LibraryItem.content_id).where(
                    LibraryItem.content_id.is_not(None), LibraryItem.archived_at.is_(None)
                )
            )
        ).scalars()
    )
    fav = set((await db.execute(select(ContentItem.id).where(ContentItem.is_favorited.is_(True)))).scalars())
    return lib | fav


async def maintain(db: AsyncSession, *, now: datetime | None = None, limit: int = 20) -> dict[str, int]:
    """每小时：收藏 / 项目来源的评论在首次采集 24 小时后刷新一次；未收藏内容的评论 30 天后删除。"""
    now = now or datetime.now(UTC)
    kept = await _kept_content_ids(db)
    refreshed = 0
    if kept:
        rows = (
            (
                await db.execute(
                    select(ContentItem).where(
                        ContentItem.id.in_(kept),
                        ContentItem.comment_state == STATE_COLLECTED,
                        ContentItem.comment_crawled_at.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for item in rows:
            if refreshed >= limit:
                break
            first = (
                await db.execute(
                    select(ContentComment.crawled_at)
                    .where(ContentComment.content_id == item.id)
                    .order_by(ContentComment.id)
                    .limit(1)
                )
            ).scalar()
            crawled = _aware(item.comment_crawled_at)
            first = _aware(first) or crawled
            # 只刷新一次：最后一次采集仍是首次采集（相差不到 1 小时）且已过 24 小时
            if crawled and first and crawled - first < timedelta(hours=1) and now - crawled >= REFRESH_AFTER:
                await collect(db, item.id, force=True)
                refreshed += 1
    cutoff = now - RETENTION
    stale = select(ContentComment.id).where(ContentComment.crawled_at < cutoff)
    if kept:
        stale = stale.where(ContentComment.content_id.not_in(kept))
    ids = list((await db.execute(stale)).scalars())
    if ids:
        await db.execute(delete(ContentComment).where(ContentComment.id.in_(ids)))
        await db.commit()
    return {"refreshed": refreshed, "deleted": len(ids)}
