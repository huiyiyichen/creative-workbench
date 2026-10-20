"""阶段 3：Obsidian 双向同步（6.8）。按演示流程：收藏 → vault 出现笔记 → 在 Obsidian 写笔记和随笔 → 回到工作台。"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.dossier import TopicDossier
from app.models.library import LibraryItem, LibraryLink, Note
from app.services import library as lib, library_files, notes, obsidian_sync as obs


@pytest.fixture(autouse=True)
def tmp_library(tmp_path, monkeypatch):
    monkeypatch.setattr(library_files, "LIBRARY_ROOT", tmp_path / "library")


@pytest.fixture
def vault(tmp_path):
    p = tmp_path / "MyVault"
    p.mkdir()
    return p


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 120), (200, 30, 40)).save(buf, "PNG")
    return buf.getvalue()


def test_pure_helpers():
    assert obs.safe_name('a/b:c*?"<>|#^[x]') == "a b c x"
    assert obs.safe_name("   ") == "未命名"
    fm, body = obs.split_frontmatter(
        "---\ncw_id: item-1\ntags: [a, b]\n---\n# T\n\n## 我的笔记\n\n你好\n\n## 关联\n\n- x\n"
    )
    assert fm == {"cw_id": "item-1", "tags": ["a", "b"]}
    assert obs.sections(body) == {"我的笔记": "你好", "关联": "- x"}
    secs = obs.parse_day_file("# 随笔\n\n## 09:05 ^cw-3\n\n第一条\n\n## 21:40\n\n新写的 #灵感\n")
    assert secs == [
        {"hh": 9, "mm": 5, "id": 3, "body": "第一条"},
        {"hh": 21, "mm": 40, "id": None, "body": "新写的 #灵感"},
    ]
    assert (
        obs.open_url("My Vault", "收藏/海报.md")
        == "obsidian://open?vault=My%20Vault&file=%E5%88%9B%E6%84%8F%E5%B7%A5%E4%BD%9C%E5%8F%B0/%E6%94%B6%E8%97%8F/%E6%B5%B7%E6%8A%A5.md"
    )


@pytest.mark.asyncio
async def test_disabled_without_vault(db):
    assert await obs.sync_once(db) == {"enabled": False}


@pytest.mark.asyncio
async def test_set_settings_validates(db, vault):
    with pytest.raises(obs.ObsidianError):
        await obs.set_settings(db, str(vault / "nope"))
    s = await obs.set_settings(db, str(vault), "http://127.0.0.1:3000/")
    assert s["vault_name"] == "MyVault" and s["app_url"] == "http://127.0.0.1:3000"
    assert (vault / obs.ROOT).is_dir()


@pytest.mark.asyncio
async def test_round_trip(db, vault):
    await obs.set_settings(db, str(vault))
    prompt = await lib.add_text(db, "a cinematic portrait, rim light", kind="prompt", title="电影感人像")
    poster = await lib.add_file(db, _png(), "bauhaus.png", title="包豪斯海报")
    await db.commit()
    note = await notes.create_note(
        db, "想到 #选题 [[包豪斯海报]]", created_at=datetime(2026, 10, 18, 6, 32, tzinfo=UTC)
    )
    dossier = TopicDossier(kind="manual", title="AI 视频", query="AI 视频", followed=True)
    db.add(dossier)
    await db.commit()

    stats = await obs.sync_once(db)
    assert stats["enabled"] and stats["items"] == 2 and stats["days"] == 1 and stats["topics"] == 1
    root = vault / obs.ROOT

    # 1) vault 出现笔记：frontmatter、摘要、关联、缩略图
    await db.refresh(poster)
    assert poster.obsidian_path == "素材/包豪斯海报.md"
    text = (root / poster.obsidian_path).read_text("utf-8")
    assert f"cw_id: item-{poster.id}" in text and "授权: 未知" in text
    assert "![[_附件/" in text and list((root / "_附件").glob("*.webp"))
    assert "双链：[[2026-10-18#^cw-%d]]" % note.id in text  # 随笔里的 [[ ]] 反映到条目的「关联」
    day = (root / "随笔" / "2026-10-18.md").read_text("utf-8")
    assert f"## 14:32 ^cw-{note.id}" in day  # 本地时间（UTC+8）
    assert (root / "主题" / "AI 视频.md").exists()
    assert (root / "提示词" / "电影感人像.md").exists()

    # 2) 再同步一次不改动任何文件
    again = await obs.sync_once(db)
    assert again["written"] == 0 and again["items_read"] == 0

    # 3) 在 Obsidian 里：写「我的笔记」+ 手写双链 + 改标签；随笔改一条、加一条；新建一篇笔记
    edited = text.replace("## 我的笔记\n\n", "## 我的笔记\n\n配色可以借给 [[电影感人像]]\n\n")
    edited = edited.replace("cw_id:", "tags:\n- 海报\n- 包豪斯\ncw_id:", 1)
    (root / poster.obsidian_path).write_text(edited, "utf-8")
    day = day.replace("想到 #选题 [[包豪斯海报]]", "想到 #选题 [[包豪斯海报]] 改过了")
    day += "\n## 22:10\n\n在 Obsidian 里加的 #灵感\n"
    (root / "随笔" / "2026-10-18.md").write_text(day, "utf-8")
    (root / "临时想法.md").write_text("一个新点子", "utf-8")

    stats = await obs.sync_once(db)
    assert stats["items_read"] == 1 and stats["notes_updated"] == 1 and stats["notes_created"] == 1
    assert stats["files_read"] == 1

    # 4) 回到工作台
    await db.refresh(poster)
    assert poster.my_notes == "配色可以借给 [[电影感人像]]"
    assert poster.tags == ["海报", "包豪斯"]
    wl = (
        (
            await db.execute(
                select(LibraryLink).where(
                    LibraryLink.from_type == "item",
                    LibraryLink.from_id == poster.id,
                    LibraryLink.relation == "wikilink",
                )
            )
        )
        .scalars()
        .all()
    )
    assert [(link.to_type, link.to_id) for link in wl] == [("item", prompt.id)]
    await db.refresh(note)
    assert note.body.endswith("改过了") and note.obsidian_synced_at is not None
    created = (await db.execute(select(Note).where(Note.source == "obsidian"))).scalar_one()
    assert created.body == "在 Obsidian 里加的 #灵感" and created.tags == ["灵感"]
    file_note = (await db.execute(select(Note).where(Note.source == obs.FILE_NOTE_SOURCE))).scalar_one()
    assert file_note.body == "临时想法\n\n一个新点子"

    # 5) 字段归属：「我的笔记」原样保留；新小节写回时补上锚点；整篇笔记不进日文件
    text2 = (root / poster.obsidian_path).read_text("utf-8")
    assert "配色可以借给 [[电影感人像]]" in text2 and "- 海报" in text2
    day2 = (root / "随笔" / "2026-10-18.md").read_text("utf-8")
    assert f"## 22:10 ^cw-{created.id}" in day2 and "临时想法" not in day2
    # 工作台改了条目，Obsidian 那边的「我的笔记」也不丢
    await lib.update_item(db, poster.id, {"license": "commercial"})
    await obs.sync_once(db)
    text3 = (root / poster.obsidian_path).read_text("utf-8")
    assert "授权: 可商用" in text3 and "配色可以借给 [[电影感人像]]" in text3

    # 6) 再改那篇新建的笔记，更新同一条随笔而不是新增
    (root / "临时想法.md").write_text("一个新点子，补充", "utf-8")
    await obs.sync_once(db)
    await db.refresh(file_note)
    assert file_note.body.endswith("补充")
    assert len((await db.execute(select(Note).where(Note.source == obs.FILE_NOTE_SOURCE))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_name_collision(db, vault):
    await obs.set_settings(db, str(vault))
    a = await lib.add_text(db, "prompt one", kind="prompt", title="同名")
    b = await lib.add_text(db, "prompt two", kind="prompt", title="同名")
    await db.commit()
    await obs.sync_once(db)
    rows = {i.id: i.obsidian_path for i in (await db.execute(select(LibraryItem))).scalars()}
    assert rows[a.id] == "提示词/同名.md" and rows[b.id] == "提示词/同名 2.md"


# ── 图谱（6.7） ──


@pytest.mark.asyncio
async def test_graph_global_and_local(db):
    from app.services import library_graph

    a = await lib.add_text(db, "p1", kind="prompt", title="A")
    b = await lib.add_text(db, "p2", kind="prompt", title="B")
    c = await lib.add_text(db, "p3", kind="prompt", title="C")
    d = await lib.add_text(db, "p4", kind="prompt", title="D")
    for it in (a, b):
        it.tags = ["海报"]
    await db.commit()
    note = await notes.create_note(db, "看 [[C]]")
    g = await library_graph.build_graph(db)
    keys = {n["key"] for n in g["nodes"]}
    assert {f"item:{a.id}", f"item:{d.id}", f"note:{note.id}"} <= keys
    rel = {(e["source"], e["target"]): e["relation"] for e in g["edges"]}
    assert rel[tuple(sorted([f"item:{a.id}", f"item:{b.id}"]))] == "same_tag"
    assert rel[tuple(sorted([f"item:{c.id}", f"note:{note.id}"]))] == "wikilink"
    deg = {n["key"]: n["degree"] for n in g["nodes"]}
    assert deg[f"item:{d.id}"] == 0

    local = await library_graph.build_graph(db, center=f"note:{note.id}", depth=1)
    assert {n["key"] for n in local["nodes"]} == {f"note:{note.id}", f"item:{c.id}"}
    only_items = await library_graph.build_graph(db, types=["item"])
    assert all(n["type"] == "item" for n in only_items["nodes"])
    with pytest.raises(ValueError):
        library_graph.parse_key("bad:1")


@pytest.mark.asyncio
async def test_graph_similar_edges_from_vectors(db):
    import numpy as np

    from app.models.content import ContentItem, ContentStatus
    from app.models.content_observation import ContentEmbedding
    from app.models.library import LibraryItem
    from app.services import embeddings
    from app.services.library_graph import build_graph

    vecs = [np.array([1, 0, 0], np.float32), np.array([0.95, 0.1, 0], np.float32), np.array([0, 0, 1], np.float32)]
    items = []
    for i, v in enumerate(vecs):
        c = ContentItem(
            title=f"内容{i}", url=f"https://ex.com/sim{i}", status=ContentStatus.PENDING, crawled_at=datetime.now(UTC)
        )
        db.add(c)
        await db.flush()
        db.add(ContentEmbedding(content_id=c.id, model=embeddings.MODEL_NAME, vector=embeddings.to_bytes(v)))
        li = LibraryItem(kind="article", title=f"收藏{i}", content_id=c.id)
        db.add(li)
        await db.flush()
        items.append(li.id)
    await db.commit()
    g = await build_graph(db, types=["item"])
    sim = {(e["source"], e["target"]) for e in g["edges"] if e["relation"] == "similar"}
    assert sim == {tuple(sorted([f"item:{items[0]}", f"item:{items[1]}"]))}
