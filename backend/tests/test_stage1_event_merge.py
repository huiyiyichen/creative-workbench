"""阶段 1：本地向量事件归并（改造方案 4.1）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.models.content import ContentItem, ContentStatus
from app.models.content_event import ContentEventGroup, ContentEventMember
from app.models.content_observation import ContentJourney
from app.services import embeddings, event_merge


def _vec(*xs: float) -> np.ndarray:
    v = np.zeros(embeddings.DIM, dtype=np.float32)
    v[: len(xs)] = xs
    return v / np.linalg.norm(v)


TOPICS = {"opus": _vec(1, 0.05), "opus2": _vec(1, 0.1), "opus3": _vec(1, 0.12), "weather": _vec(0, 1)}


@pytest.fixture
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "available", lambda: True)

    def fake_embed(texts, batch_size=32):
        return np.vstack([TOPICS[t.split("\n")[0].split()[0]] for t in texts])

    monkeypatch.setattr(embeddings, "embed", fake_embed)


def _item(n: int, title: str, **kw) -> ContentItem:
    base = {
        "title": title,
        "url": f"https://example.com/{n}",
        "status": ContentStatus.PENDING,
        "content_hash": f"h{n}",
        "crawled_at": datetime.now(UTC) - timedelta(minutes=10 - n),
        "published_at": datetime.now(UTC) - timedelta(hours=5 - n),
        "skip_analysis": False,
        "analysis_level": "none",
        "comment_state": "none",
    }
    base.update(kw)
    return ContentItem(**base)


@pytest.mark.asyncio
async def test_merge_groups_similar_and_picks_representative(db, fake_embeddings):
    db.add_all(
        [
            _item(1, "opus 发布", platform="hn", triage_score=50, triage_signals={"freshness": 1.0}),
            _item(2, "opus2 视频", platform="bilibili", raw_content="很长的正文" * 400, triage_score=40),
            _item(3, "weather 晴", platform="web"),
            _item(4, "opus3 实测", platform="youtube", full_eligible=True),
        ]
    )
    await db.commit()
    stats = await event_merge.merge_recent_events(db)
    assert stats == {"embedded": 4, "merged": 2, "events_created": 1}

    group = (await db.execute(select(ContentEventGroup))).scalar_one()
    members = (await db.execute(select(ContentEventMember.content_id))).scalars().all()
    assert group.canonical_content_id == 1  # 规范条目仍是最早出现的
    assert sorted(members) == [2, 4]
    assert group.representative_content_id == 2  # 分析代表：正文最全

    items = {c.id: c for c in (await db.execute(select(ContentItem))).scalars()}
    assert items[2].full_eligible is None
    assert items[1].full_eligible is False and items[4].full_eligible is False  # 代表以外不再单独分析
    assert items[4].quick_result["event"] == {"id": group.id, "representative": 2}
    assert items[3].full_eligible is None
    assert items[2].triage_signals["coverage"] == pytest.approx(2 / 3, abs=1e-3)  # 3 个平台
    stages = (await db.execute(select(ContentJourney.stage))).scalars().all()
    assert stages.count("event") == 2

    again = await event_merge.merge_recent_events(db)
    assert again == {"embedded": 0, "merged": 0, "events_created": 0}


@pytest.mark.asyncio
async def test_analyzed_representative_is_kept(db, fake_embeddings):
    db.add_all(
        [
            _item(1, "opus 发布", analysis_level="full", status=ContentStatus.ANALYZED),
            _item(2, "opus2 视频", raw_content="长" * 9000),
        ]
    )
    await db.commit()
    await event_merge.merge_recent_events(db)
    group = (await db.execute(select(ContentEventGroup))).scalar_one()
    assert group.representative_content_id == 1


@pytest.mark.asyncio
async def test_merge_skips_when_model_unavailable(db):
    db.add(_item(1, "opus 发布"))
    await db.commit()
    result = await event_merge.merge_recent_events(db)
    assert result["skipped"] == "embedding_unavailable"


def test_best_match_respects_threshold():
    pool = np.vstack([TOPICS["opus"], TOPICS["weather"]])
    assert event_merge.best_match(TOPICS["opus2"], [1, 2], pool, exclude=9, threshold=0.9)[0] == 1
    assert event_merge.best_match(TOPICS["weather"] * 0 + _vec(0.3, 0.7), [1], pool[:1], exclude=9, threshold=0.9) is None
