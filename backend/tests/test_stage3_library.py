"""阶段 3：灵感库、随笔、风格与模板、旧收藏夹迁移、素材收件箱。"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image, PngImagePlugin
from sqlalchemy import select

from app.api.v1 import library as library_api
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.content import ContentItem, ContentStatus
from app.models.dossier import TopicDossier
from app.models.favorite import FavoriteItem
from app.models.library import LibraryItem, LibraryLink
from app.services import library as lib, library_files, library_migration, notes, styles
from app.services.auth_service import get_local_user


@pytest.fixture(autouse=True)
def tmp_library(tmp_path, monkeypatch):
    monkeypatch.setattr(library_files, "LIBRARY_ROOT", tmp_path / "library")
    return tmp_path / "library"


def _png(color=(220, 40, 50), *, params: str | None = None, size=(400, 300)) -> bytes:
    img = Image.new("RGB", size, color)
    for x in range(0, size[0] // 2):
        for y in range(0, size[1] // 3):
            img.putpixel((x, y), (20, 60, 200))
    buf = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    if params:
        info.add_text("parameters", params)
    img.save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


# ── 纯函数 ──


def test_parse_link_platforms():
    assert lib.parse_link("https://www.bilibili.com/video/BV1xx411c7mD?p=1") == ("bilibili", "BV1xx411c7mD")
    assert lib.parse_link("https://youtu.be/dQw4w9WgXcQ") == ("youtube", "dQw4w9WgXcQ")
    assert lib.parse_link("https://www.youtube.com/watch?v=abc123XYZ") == ("youtube", "abc123XYZ")
    assert lib.parse_link("https://github.com/remotion-dev/remotion/tree/main") == ("github", "remotion-dev/remotion")
    assert lib.parse_link("https://news.ycombinator.com/item?id=42") == ("hn", "42")
    assert lib.parse_link("https://www.xiaohongshu.com/explore/66aa11bb") == ("xiaohongshu", "66aa11bb")
    assert lib.parse_link("https://www.douyin.com/video/7300000000") == ("douyin", "7300000000")
    assert lib.parse_link("https://example.com/a") == ("web", None)


def test_extract_prompts_and_repos():
    text = "这期用的提示词：a cinematic shot of a red fox in snow, 35mm, golden hour\n\n代码在 https://github.com/foo/bar 和 https://github.com/foo/bar."
    prompts, repos = lib.extract_prompts_and_repos(text)
    assert prompts == ["a cinematic shot of a red fox in snow, 35mm, golden hour"]
    assert repos == ["foo/bar"]


def test_parse_note_tags_links_urls():
    p = notes.parse_note(
        "今天想到 #选题 #AI视频 关于 [[包豪斯海报]] 和 [[2026-10-18#^cw-12|上次]] 看 https://example.com/x 。\n```#not-a-tag```"
    )
    assert p["tags"] == ["选题", "AI视频"]
    assert p["wikilinks"] == ["包豪斯海报", "2026-10-18#^cw-12"]
    assert p["urls"] == ["https://example.com/x"]


def test_generation_meta_and_thumbs():
    params = "a red fox, cinematic\nNegative prompt: blurry, lowres\nSteps: 30, Sampler: DPM++ 2M, CFG scale: 7, Seed: 42, Model: sdxl_base"
    sf = library_files.store_bytes(_png(params=params), "fox.png")
    assert sf.generated and sf.meta["prompt"] == "a red fox, cinematic"
    assert sf.meta["negative_prompt"] == "blurry, lowres"
    assert sf.meta["params"]["Seed"] == "42" and sf.meta["model"] == "sdxl_base"
    assert sf.width == 400 and sf.dominant_color and len(sf.palette) >= 2
    assert library_files.abs_path(sf.thumb_small).exists() and sf.thumb_large.endswith("-960.webp")
    assert library_files.classify("a.ttf") == "font" and library_files.classify("a.mp3") == "audio"
    assert lib.color_distance("#ff0000", "#fe0101") < lib.color_distance("#ff0000", "#0000ff")


# ── 数据库 ──


@pytest.mark.asyncio
async def test_library_flow(db):
    c = ContentItem(
        title="用 Opus 5.5 做 MV",
        url="https://www.bilibili.com/video/BV1aa411c7aa",
        status=ContentStatus.PENDING,
        platform="bilibili",
        media_type="video",
        author="像素与噪点",
        summary="提示词：a neon city at night, rain, reflections, wide shot\n\n工程 https://github.com/kit/opus-mv",
        crawled_at=datetime.now(UTC),
        analysis_level="none",
        comment_state="none",
    )
    db.add(c)
    await db.commit()

    item = await lib.add_from_content(db, c.id)
    assert item.kind == "video" and item.content_id == c.id
    await db.refresh(c)
    assert c.is_favorited is True
    again = await lib.add_from_content(db, c.id)
    assert again.id == item.id  # 同一条只收一次
    children = (await db.execute(select(LibraryItem).where(LibraryItem.import_method == "extracted"))).scalars().all()
    assert {ch.kind for ch in children} == {"prompt", "repo"}
    detail = await lib.get_item(db, item.id)
    assert {r["relation"] for r in detail["related"]} == {"extracted"}

    gen = await lib.add_file(db, _png(params="a red fox\nSteps: 20, Seed: 1"), "fox.png")
    assert gen.kind == "generated" and gen.license == "ai" and gen.body == "a red fox"
    dup = await lib.add_file(db, _png(params="a red fox\nSteps: 20, Seed: 1"), "copy.png")
    assert dup.id == gen.id
    plain = await lib.add_file(db, _png(color=(240, 220, 30)), "poster.png", title="包豪斯海报")
    assert plain.kind == "asset" and plain.asset_kind == "image" and plain.license == "unknown"

    await lib.update_item(db, plain.id, {"tags": ["包豪斯"], "license": "reference"})
    found = await lib.list_items(db, q="包豪斯 海报")
    assert [i["id"] for i in found["items"]] == [plain.id]
    by_tag = await lib.list_items(db, tag="包豪斯")
    assert by_tag["total"] == 1
    assets = await lib.list_items(db, kind="asset")
    assert {i["id"] for i in assets["items"]} == {gen.id, plain.id}
    by_color = await lib.list_items(db, color="#1e3cc8")
    assert by_color["total"] >= 1
    assert await lib.bulk_license(db, [gen.id, plain.id], "own") == 2

    board = await lib.create_board(db, "包豪斯")
    assert await lib.add_to_board(db, board.id, [plain.id, gen.id, plain.id]) == 2
    boards = await lib.list_boards(db)
    assert boards[0]["count"] == 2
    in_board = await lib.list_items(db, board_id=board.id)
    assert in_board["total"] == 2
    facets = await lib.facets(db)
    assert facets["kinds"]["asset"] == 1 and facets["licenses"]["own"] == 2

    # 随笔：#标签、[[双链]]、按标签筛选、改正文重建双链
    note = await notes.create_note(db, "这个配色可以用在片头 #配色 参考 [[包豪斯海报]]")
    links = (await db.execute(select(LibraryLink).where(LibraryLink.from_type == "note"))).scalars().all()
    assert [(link.to_type, link.to_id, link.relation) for link in links] == [("item", plain.id, "wikilink")]
    listed = await notes.list_notes(db, tag="配色")
    assert listed["days"][0]["notes"][0]["links"][0]["title"] == "包豪斯海报"
    await notes.update_note(db, note.id, "改了，不再关联 #配色")
    links = (await db.execute(select(LibraryLink).where(LibraryLink.from_type == "note"))).scalars().all()
    assert links == []
    related = await notes.related_for_note(db, note)
    assert set(related) == {"favorites", "hot"}

    await lib.archive_item(db, item.id)
    await db.refresh(c)
    assert c.is_favorited is False


@pytest.mark.asyncio
async def test_styles_seed_versions_and_catalog(db):
    assert (await styles.seed_builtins(db))["created"] >= 10
    assert (await styles.seed_builtins(db))["created"] == 0  # 幂等
    cat = await styles.catalog_entries(db)
    bauhaus = next(s for s in cat["styles"] if s["id"] == "bauhaus")
    assert bauhaus["background"] == "#F4F4F0" and bauhaus["accent"] == "#D92332" and not bauhaus["custom"]
    explainer = next(t for t in cat["templates"] if t["id"] == "explainer")
    assert explainer["beats"][0] == "问题" and explainer["modes"] == ["article"]

    # 编辑内置 → 复制成自定义
    copied = await styles.add_style_version(db, "bauhaus", {"motion_rules": "硬切"})
    assert copied["copied_from"] == "bauhaus" and copied["versions"][0]["motion_rules"] == "硬切"
    v2 = await styles.add_style_version(db, copied["key"], {"palette": [{"name": "红", "hex": "#ff0000"}]})
    assert v2["current_version"] == 2 and [v["version"] for v in v2["versions"]] == [2, 1]
    assert v2["versions"][1]["palette"] != v2["versions"][0]["palette"]  # 旧版本不变
    with pytest.raises(styles.StyleError):
        await styles.add_style_version(db, copied["key"], {"palette": [{"hex": "red"}]})
    with pytest.raises(styles.StyleError):
        await styles.archive_entry(db, "style", "bauhaus")
    mine = await styles.list_styles(db, include_builtin=False)
    assert [s["key"] for s in mine] == [copied["key"]]


@pytest.mark.asyncio
async def test_distill_style_with_fake_llm(db, monkeypatch):
    from app.services.llm import provider

    item = await lib.add_file(db, _png(color=(200, 30, 40)), "poster.png", title="海报")
    await lib.update_item(db, item.id, {"tags": ["包豪斯"]})

    async def fake_json(messages, **kw):
        assert "海报" in messages[1]["content"]
        return {
            "name": "包豪斯（我的）",
            "palette": [{"name": "红", "hex": "#d92332"}, {"name": "坏", "hex": "x"}],
            "layout_rules": "网格",
        }

    monkeypatch.setattr(provider, "call_llm_json", fake_json)
    entry = await styles.distill(db, "style", "包豪斯")
    assert entry["reference_count"] == 1 and entry["versions"][0]["palette"] == [{"name": "红", "hex": "#d92332"}]
    detail = await lib.get_item(db, item.id)
    assert any(r["relation"] == "distilled" for r in detail["related"])


@pytest.mark.asyncio
async def test_migrate_favorites_and_inbox(db, tmp_path):
    user = await get_local_user(db)
    c = ContentItem(
        title="旧收藏的文章",
        url="https://ex.com/a",
        status=ContentStatus.PENDING,
        crawled_at=datetime.now(UTC),
        analysis_level="none",
        comment_state="none",
    )
    db.add(c)
    await db.flush()
    db.add_all(
        [
            FavoriteItem(
                user_id=user.id,
                target_type="content",
                target_id=c.id,
                target_key=f"content:{c.id}",
                title=c.title,
                url=c.url,
                tags=["旧标签"],
            ),
            FavoriteItem(user_id=user.id, target_type="trend", target_key="trend:x", title="AI 视频"),
            FavoriteItem(
                user_id=user.id,
                target_type="template",
                target_key="t1",
                title="我的结构",
                snapshot={"beats": ["开场", "结尾"], "modes": ["article"]},
            ),
            FavoriteItem(
                user_id=user.id,
                target_type="style",
                target_key="s1",
                title="我的风格",
                snapshot={"colors": ["#111111", "#eeeeee"]},
            ),
            FavoriteItem(
                user_id=user.id, target_type="book", target_key="b1", title="一本书", url="https://book.example/1"
            ),
        ]
    )
    await db.commit()
    stats = await library_migration.migrate_favorites(db)
    assert stats["library"] == 2 and stats["dossiers"] == 1 and stats["templates"] == 1 and stats["styles"] == 1
    again = await library_migration.migrate_favorites(db)
    assert again["library"] == 0 and again["templates"] == 0 and again["dossiers"] == 0
    tpl_fav = (await db.execute(select(FavoriteItem).where(FavoriteItem.target_type == "template"))).scalar_one()
    tpl = await styles.get_template(db, f"favorite:template:{tpl_fav.id}")
    assert tpl["versions"][0]["structure"][0]["title"] == "开场"
    assert (
        await db.execute(select(TopicDossier).where(TopicDossier.followed.is_(True)))
    ).scalar_one().title == "AI 视频"
    migrated = (await db.execute(select(LibraryItem).where(LibraryItem.content_id == c.id))).scalar_one()
    assert migrated.tags == ["旧标签"] and migrated.import_method == "migrated"

    inbox = tmp_path / "inbox"
    await library_migration.set_inbox_dir(db, str(inbox))
    (inbox / "a.png").write_bytes(_png(color=(10, 200, 10)))
    (inbox / "notes.txt").write_text("skip")
    (inbox / "b.part").write_bytes(b"x")
    result = await library_migration.scan_inbox(db)
    assert result == {"imported": 1, "failed": 0}
    assert (inbox / library_migration.IMPORTED_DIR / "a.png").exists() and not (inbox / "a.png").exists()


@pytest.mark.asyncio
async def test_library_api(db):
    user = await get_local_user(db)
    await db.commit()
    app = FastAPI()
    app.include_router(library_api.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        r = await client.post(
            "/library/extension/save",
            json={"type": "text", "text": "a prompt about cats", "page_url": "https://ex.com", "page_title": "猫"},
        )
        assert r.status_code == 200 and r.json()["item"]["kind"] == "prompt"
        up = await client.post(
            "/library/items/upload",
            files=[("files", ("p.png", _png(), "image/png")), ("files", ("x.exe", b"MZ", "application/octet-stream"))],
        )
        body = up.json()
        assert len(body["items"]) == 2 and body["items"][0]["thumb"] is True
        iid = body["items"][0]["id"]
        f = await client.get(f"/library/items/{iid}/file")
        assert f.status_code == 200 and f.headers["content-type"] == "image/webp"
        orig = await client.get(f"/library/items/{iid}/file", params={"size": "original"})
        assert orig.content[:4] == b"\x89PNG"
        n = await client.post("/notes", json={"body": "灵感 #AI"})
        assert n.json()["tags"] == ["AI"] and "related" in n.json()
        lst = await client.get("/notes")
        assert lst.json()["days"][0]["notes"][0]["body"] == "灵感 #AI"
        bad = await client.post("/library/items/from-link", json={"url": "ftp://x"})
        assert bad.status_code == 422
        assert (await client.get("/library/items/99999")).status_code == 404
