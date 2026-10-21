"""爆款拆解：热词粗算、结果入灵感库、照结构建项目。"""

from __future__ import annotations

import pytest

from app.models.library import LibraryItem
from app.schemas.projects import ProjectCreate
from app.services import breakdown_service as bd, project_service as ps


def test_hot_phrases_prefers_longer_and_needs_two_comments():
    texts = ["打工人太真实了", "打工人狠狠共鸣", "真实的打工人", "只出现一次的词组"]
    words = dict(bd.hot_phrases(texts))
    assert words.get("打工人") == 3
    assert "打工" not in words  # 被「打工人」吃掉
    assert "词组" not in words


@pytest.mark.asyncio
async def test_breakdown_saves_to_library_and_caches(db, monkeypatch):
    item = LibraryItem(kind="link", title="一条爆款", url="https://example.com/a", body="开头一句反差。中间讲故事。")
    db.add(item)
    await db.commit()
    calls = []

    async def fake_llm(messages, **kw):
        calls.append(messages)
        return {
            "verdict": "反差开头 + 共鸣",
            "hook": {"text": "开头一句反差", "type": "反差", "why": "违背常识"},
            "beats": [{"name": "抛反差", "does": "第一句"}, {"name": ""}],
            "emotions": [{"point": "共鸣", "evidence": "评论"}],
            "comment_words": [{"word": "打工人", "meaning": "自嘲"}],
            "template": "1. 反差\n2. 故事",
            "titles": ["a", "b", "c", "d"],
        }

    monkeypatch.setattr("app.services.llm.call_llm_json", fake_llm)
    r = await bd.breakdown(db, library_item_id=item.id)
    assert r["item_id"] == item.id and r["hook"]["type"] == "反差"
    assert len(r["beats"]) == 1 and len(r["titles"]) == 3 and r["comments_used"] == 0
    again = await bd.breakdown(db, library_item_id=item.id)
    assert again["verdict"] == r["verdict"] and len(calls) == 1
    await db.refresh(item)
    assert item.meta["breakdown"]["template"].startswith("1.")

    p = await ps.create_project(
        db, 1, ProjectCreate(sources=[f"library:{item.id}"], intent=bd.intent_from(item.meta["breakdown"], item.title))
    )
    detail = await ps.get_project(db, p["id"])
    assert "照这个结构写" in detail.spec["brief"]["intent"]
