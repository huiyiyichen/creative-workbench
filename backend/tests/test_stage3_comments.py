"""阶段 3：条目评论（3.5）——来源识别、采集与更新、无来源 / 失败、摘要、24 小时刷新一次、30 天保留。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, ContentStatus
from app.models.content_observation import ContentComment
from app.services import comments
from app.services.platforms import Comment, PlatformError


def _content(**kw) -> ContentItem:
    base = {
        "title": "一条视频",
        "url": "https://www.bilibili.com/video/BV1aa411c7aa",
        "status": ContentStatus.PENDING,
        "platform": "bilibili",
        "platform_item_id": "BV1aa411c7aa",
        "crawled_at": datetime.now(UTC),
    }
    base.update(kw)
    return ContentItem(**base)


def test_resolve_source():
    assert comments.resolve_source(_content()) == ("bilibili", "BV1aa411c7aa")
    assert comments.resolve_source(_content(platform="hackernews", platform_item_id="42")) == ("hn", "42")
    # 老数据没有平台 id：从链接认
    assert comments.resolve_source(
        _content(platform=None, platform_item_id=None, url="https://youtu.be/abcDEF12345")
    ) == (
        "youtube",
        "abcDEF12345",
    )
    assert comments.resolve_source(_content(platform="rss", platform_item_id=None, url="https://blog.ex.com/a")) is None
    # GitHub 没有评论能力
    assert (
        comments.resolve_source(_content(platform="github", platform_item_id="a/b", url="https://github.com/a/b"))
        is None
    )


def test_comment_key_stable():
    a = Comment(text="同一条", author="甲")
    assert comments.comment_key("hn", a) == comments.comment_key("hn", Comment(text="同一条", author="甲"))
    assert comments.comment_key("hn", Comment(text="x", id="123")) == "123"


@pytest.mark.asyncio
async def test_collect_update_and_states(db, monkeypatch):
    c = _content()
    db.add(c)
    await db.commit()
    likes = {"v": 5}

    async def fake_fetch(_db, platform, pid):
        assert (platform, pid) == ("bilibili", "BV1aa411c7aa")
        return [
            Comment(text="讲得清楚", author="甲", likes=likes["v"], id="r1"),
            Comment(text="BGM 是什么", author="乙", likes=30, id="r2"),
            Comment(text="   ", author="丙", likes=1, id="r3"),  # 空评论跳过
        ]

    monkeypatch.setattr(comments, "_fetch", fake_fetch)
    out = await comments.collect(db, c.id)
    assert out["state"] == "collected" and out["source"] == "bilibili"
    assert [x["text"] for x in out["items"]] == ["BGM 是什么", "讲得清楚"]  # 按点赞排序

    # 已采集：不加 force 不重新请求
    likes["v"] = 99
    await comments.collect(db, c.id)
    assert (
        await db.execute(select(ContentComment.like_count).where(ContentComment.platform_comment_id == "r1"))
    ).scalar() == 5
    # 刷新：只更新点赞数，不重复插入
    out = await comments.collect(db, c.id, force=True)
    assert len(out["items"]) == 2 and out["items"][0]["likes"] == 99

    # 失败：状态标记失败并带原因
    async def boom(*_a):
        raise PlatformError("B站 限流（429）")

    monkeypatch.setattr(comments, "_fetch", boom)
    out = await comments.collect(db, c.id, force=True)
    assert out["state"] == "failed" and "429" in out["error"] and len(out["items"]) == 2

    # 无评论来源
    rss = _content(platform="rss", platform_item_id=None, url="https://blog.ex.com/a")
    db.add(rss)
    await db.commit()
    out = await comments.collect(db, rss.id)
    assert out["state"] == "unavailable" and out["items"] == []


@pytest.mark.asyncio
async def test_digest_keeps_only_real_ids(db, monkeypatch):
    c = _content()
    db.add(c)
    await db.commit()
    with pytest.raises(comments.CommentError):
        await comments.digest(db, c.id)
    db.add_all(
        [
            ContentComment(content_id=c.id, platform="bilibili", platform_comment_id="a", text="求 BGM", like_count=10),
            ContentComment(
                content_id=c.id, platform="bilibili", platform_comment_id="b", text="教程太快", like_count=3
            ),
        ]
    )
    await db.commit()
    ids = [row.id for row in (await db.execute(select(ContentComment).order_by(ContentComment.id))).scalars()]

    from app.services.llm import provider

    async def fake_llm(messages, **kw):
        assert kw["scene"] == "comment_digest" and f"[{ids[0]}]" in messages[1]["content"]
        return {"points": [{"text": "观众想要 BGM", "comment_ids": [ids[0], 9999]}, {"text": " "}]}

    monkeypatch.setattr(provider, "call_llm_json", fake_llm)
    d = await comments.digest(db, c.id)
    assert d["points"] == [{"text": "观众想要 BGM", "comment_ids": [ids[0]]}] and d["based_on"] == 2
    await db.refresh(c)
    assert c.comment_digest["based_on"] == 2


@pytest.mark.asyncio
async def test_maintain_refresh_once_and_retention(db, monkeypatch):
    now = datetime.now(UTC)
    kept = _content(is_favorited=True, comment_state="collected", comment_crawled_at=now - timedelta(hours=25))
    other = _content(platform_item_id="BV2", url="https://www.bilibili.com/video/BV2", comment_state="collected")
    db.add_all([kept, other])
    await db.commit()
    db.add_all(
        [
            ContentComment(
                content_id=kept.id,
                platform="bilibili",
                platform_comment_id="k1",
                text="留着",
                crawled_at=now - timedelta(days=40),
            ),
            ContentComment(
                content_id=other.id,
                platform="bilibili",
                platform_comment_id="o1",
                text="过期",
                crawled_at=now - timedelta(days=31),
            ),
            ContentComment(
                content_id=other.id,
                platform="bilibili",
                platform_comment_id="o2",
                text="还新",
                crawled_at=now - timedelta(days=2),
            ),
        ]
    )
    # 收藏的那条首次采集也是 25 小时前
    kept_first = (
        await db.execute(select(ContentComment).where(ContentComment.platform_comment_id == "k1"))
    ).scalar_one()
    kept_first.crawled_at = now - timedelta(hours=25)
    await db.commit()
    calls = []

    async def fake_fetch(_db, platform, pid):
        calls.append(pid)
        return [Comment(text="留着", likes=7, id="k1")]

    monkeypatch.setattr(comments, "_fetch", fake_fetch)
    stats = await comments.maintain(db, now=now)
    assert stats == {"refreshed": 1, "deleted": 1}
    left = {r.platform_comment_id for r in (await db.execute(select(ContentComment))).scalars()}
    assert left == {"k1", "o2"}
    # 只刷新一次
    stats = await comments.maintain(db, now=now + timedelta(days=2))
    assert stats["refreshed"] == 0 and calls == ["BV1aa411c7aa"]
