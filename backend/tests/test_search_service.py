"""全局搜索与按关键词现抓。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, ContentStatus
from app.models.library import LibraryItem, Note
from app.models.source import Source, SourceStatus
from app.schemas.projects import ProjectCreate
from app.services import content_pipeline, project_service as ps, search_service


def test_snippet_case_insensitive_and_trimmed():
    text = "前面一大段" * 20 + "Claude Code 的新功能" + "后面" * 30
    s = search_service.snippet(text, "claude code", width=5)
    assert s.startswith("…") and "Claude Code" in s and s.endswith("…")
    assert search_service.snippet(None, "x") is None
    assert search_service.snippet("没有命中", "zz") == "没有命中"


@pytest.mark.asyncio
async def test_search_all_groups(test_session_factory):
    async with test_session_factory() as db:
        now = datetime.now(UTC)
        db.add_all(
            [
                ContentItem(
                    title="智能体编程实测", url="https://ex.com/1", status=ContentStatus.PENDING, crawled_at=now
                ),
                ContentItem(
                    title="别的",
                    url="https://ex.com/2",
                    summary="正文里提到智能体",
                    status=ContentStatus.PENDING,
                    crawled_at=now,
                ),
                ContentItem(title="无关", url="https://ex.com/3", status=ContentStatus.PENDING, crawled_at=now),
                LibraryItem(kind="article", title="收藏：智能体综述"),
                LibraryItem(kind="article", title="已归档智能体", archived_at=now),
                Note(body="今天想到：智能体可以帮我剪片\n第二行"),
                Note(body="删掉的智能体随笔", deleted_at=now),
                ContentItem(title="100% 无关", url="https://ex.com/4", status=ContentStatus.PENDING, crawled_at=now),
            ]
        )
        await db.commit()
        await ps.create_project(db, 1, ProjectCreate(theme="智能体做视频"))

        data = await search_service.search_all(db, "  智能体 ")
        g = data["groups"]
        assert data["q"] == "智能体"
        assert {c["title"] for c in g["contents"]} == {"智能体编程实测", "别的"}
        other = next(c for c in g["contents"] if c["title"] == "别的")
        assert other["snippet"] and "智能体" in other["snippet"]
        assert [i["title"] for i in g["library"]] == ["收藏：智能体综述"]
        assert g["library"][0]["href"].startswith("/library?open=")
        assert len(g["notes"]) == 1 and g["notes"][0]["title"] == "今天想到：智能体可以帮我剪片"
        assert len(g["projects"]) == 1 and g["projects"][0]["href"].startswith("/projects/")
        assert data["total"] == sum(len(v) for v in g.values())

        only = await search_service.search_all(db, "智能体", groups=("notes",))
        assert set(only["groups"]) == {"notes"}
        # % 被转义，不会匹配一切
        pct = await search_service.search_all(db, "%", groups=("contents",))
        assert [c["title"] for c in pct["groups"]["contents"]] == ["100% 无关"]
        with pytest.raises(ValueError):
            await search_service.search_all(db, "   ")


@pytest.mark.asyncio
async def test_crawl_keyword_once_then_track(test_session_factory, monkeypatch):
    calls: list[tuple[str, list[str]]] = []

    async def fake_ingest(source, db):
        calls.append((source.query, list(source.platforms or [])))
        source.status = SourceStatus.ACTIVE  # 真实 ingest 结束时会把 SYNCING 改回来
        db.add(
            ContentItem(
                title=f"{source.query} 第{len(calls)}次",
                url=f"https://ex.com/k{len(calls)}",
                status=ContentStatus.PENDING,
                crawled_at=datetime.now(UTC),
                source_id=source.id,
                platform="bilibili",
            )
        )
        await db.flush()
        return {"fetched": 1, "new": 1, "duplicates": 0}

    monkeypatch.setattr(content_pipeline, "ingest_from_source", fake_ingest)
    import app.scheduler  # noqa: F401 - 先加载调度器，避免 _post_sync_pipeline 循环导入

    monkeypatch.setattr("app._post_sync_pipeline._request_post_sync_pipeline", lambda stats: None)
    monkeypatch.setattr("app.services.source_registry.searchable_platforms", lambda: ["bilibili", "youtube", "douyin"])

    async with test_session_factory() as db:
        r = await search_service.crawl_keyword(db, "AI 短片", platforms=["bilibili", "nope"])
        assert r["created"] and not r["tracking"] and r["new"] == 1 and r["status"] == "success"
        assert r["platforms"] == ["bilibili"]
        assert [i["title"] for i in r["items"]] == ["AI 短片 第1次"]

        # 同一个词（大小写 / 空格不同）复用信源；第二次选择持续追踪
        r2 = await search_service.crawl_keyword(db, "ai  短片", track=True)
        assert not r2["created"] and r2["source_id"] == r["source_id"] and r2["tracking"]
        assert calls[-1] == ("AI 短片", ["bilibili", "youtube", "douyin"])
        assert len(r2["items"]) == 2

        # 已追踪的词再抓一次不会被停用
        r3 = await search_service.crawl_keyword(db, "AI 短片")
        assert r3["tracking"]
        sources = (await db.execute(select(Source).where(Source.kind == "keyword"))).scalars().all()
        assert len(sources) == 1

        with pytest.raises(ValueError):
            await search_service.crawl_keyword(db, "x", platforms=["nope"])
