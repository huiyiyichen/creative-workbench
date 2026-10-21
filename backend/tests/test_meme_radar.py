"""今日梗雷达：没材料不调模型；按北京时间每天缓存一次；结果规整。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.trending import TrendingItem
from app.services import meme_service


@pytest.mark.asyncio
async def test_empty_material_skips_llm(db, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("不该调模型")

    monkeypatch.setattr("app.services.llm.call_llm_json", boom)
    r = await meme_service.radar(db)
    assert r["items"] == [] and r["reason"]


@pytest.mark.asyncio
async def test_radar_cached_per_day(db, monkeypatch):
    now = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)
    for i, t in enumerate(["班味太重了怎么办", "去班味指南走红", "年轻人开始去班味"]):
        db.add(
            TrendingItem(
                source="weibo", category="hot", rank=i, title=t, hot_value=100 - i, batch_id="b", fetched_at=now
            )
        )
    await db.commit()
    calls = []

    async def fake(messages, **kw):
        calls.append(messages)
        assert "班味" in messages[1]["content"]
        return {
            "memes": [
                {
                    "word": "班味",
                    "meaning": "上班上出来的疲惫感",
                    "usage": "周末去班味",
                    "heat": 9,
                    "platforms": ["小红书"],
                },
                {"word": ""},
                {"word": "新梗", "heat": "x"},
            ]
        }

    monkeypatch.setattr("app.services.llm.call_llm_json", fake)
    r = await meme_service.radar(db, now=now)
    assert r["date"] == "2026-10-21" and [m["word"] for m in r["items"]] == ["班味", "新梗"]
    assert r["items"][0]["heat"] == 3 and r["items"][1]["heat"] == 1
    again = await meme_service.radar(db, now=now)
    assert again["items"] == r["items"] and len(calls) == 1
    await meme_service.radar(db, now=now, refresh=True)
    assert len(calls) == 2
