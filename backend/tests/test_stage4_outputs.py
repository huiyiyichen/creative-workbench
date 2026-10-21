"""阶段 4：平台改写字数约束与 HTML 清洗、提示词包内容完整。"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.models.library import LibraryItem
from app.schemas.projects import AssetAdd, DraftSave, OutputCreate, OutputPatch, ProjectCreate
from app.schemas.studio import StudioDraft, StudioShot
from app.services import output_rules as rules, output_service as os_, project_service as ps


def test_xhs_limits_and_truncate():
    raw = {
        "title": "这是一个明显超过二十个字的小红书标题需要被截断才行",
        "body": "字" * 1200,
        "tags": ["a", "b"],
        "cover_text": "封面文案也太长了超过十二字",
    }
    issues = {i["field"] for i in rules.check("xhs", raw)}
    assert issues == {"title", "body", "tags", "cover_text"}
    c = os_.normalize_platform("xhs", raw)
    assert len(c["title"]) == 20 and len(c["body"]) == 1000 and len(c["cover_text"]) == 12
    assert any(w.startswith("已截断") for w in c["warnings"])
    assert any("话题" in w for w in c["warnings"])  # 话题太少截断不了，保留提示


def test_wechat_html_sanitized():
    html = '<h2>小标题</h2><p onclick="x()">正文<script>alert(1)</script><a href="javascript:alert(1)">坏链</a><a href="https://ok">好链</a></p><iframe src="https://e"></iframe><img src="https://i/1.png" onerror="x">'
    out = os_.sanitize_wechat_html(html)
    assert "<script" not in out and "onclick" not in out and "iframe" not in out and "onerror" not in out
    assert "javascript:" not in out and 'href="https://ok"' in out and "<h2>小标题</h2>" in out


def test_zhihu_sources_appended():
    body = os_.zhihu_with_sources("正文", [{"snapshot": {"title": "A", "url": "https://a"}}])
    assert body.endswith("## 来源\n\n1. [A](https://a)")


@pytest.mark.asyncio
async def test_generate_platform_retries_once(db, monkeypatch):
    p = await ps.create_project(db, 1, ProjectCreate(theme="主题"))
    await ps.save_draft(db, p["id"], DraftSave(draft=StudioDraft(body="一段正文")))
    await ps.finalize(db, p["id"])
    out = await ps.create_output(db, p["id"], OutputCreate(kind="xhs"))
    calls = []

    async def fake(messages):
        calls.append(messages)
        if len(calls) == 1:
            return {
                "title": "超过二十个字的标题超过二十个字的标题啊啊啊啊",
                "body": "正文",
                "tags": ["a", "b", "c"],
            }, {}
        return {"title": "短标题", "body": "正文", "tags": ["a", "b", "c"], "cover_text": "封面"}, {"model": "m"}

    monkeypatch.setattr(os_, "_call_model", fake)
    r = await os_.generate_platform(db, out["id"])
    assert len(calls) == 2 and "超出平台限制" in calls[1][-1]["content"]
    assert r["content"]["title"] == "短标题" and r["content"]["warnings"] == [] and r["based_on_version"] == 1
    assert (await ps.project_view(db, p["id"]))["finalized_version"] == 1


@pytest.mark.asyncio
async def test_prompt_bundle_complete(db, tmp_path, monkeypatch):
    from app.services import library_files

    monkeypatch.setattr(library_files, "LIBRARY_ROOT", tmp_path)
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "a.png").write_bytes(b"png")
    p = await ps.create_project(db, 1, ProjectCreate(theme="讲解", mode="animation_video"))
    draft = StudioDraft(
        title="讲解",
        logline="一句话",
        body="旁白全文",
        shots=[StudioShot(seconds=3, visual="开场|数字", audio="先看一个数字", caption="601", prompt="几何色块")],
    )
    await ps.save_draft(db, p["id"], DraftSave(draft=draft))
    item = LibraryItem(
        kind="image", title="参考海报", file_path="img/a.png", file_name="a.png", license="reference_only"
    )
    db.add(item)
    await db.commit()
    await ps.add_asset(db, p["id"], AssetAdd(library_item_id=item.id))
    await ps.finalize(db, p["id"])
    out = await ps.create_output(db, p["id"], OutputCreate(kind="prompt_bundle"))
    await ps.patch_output(db, out["id"], OutputPatch(settings={"target": "claude_code", "aspect_ratio": "9:16"}))
    md, media, name = await os_.bundle(db, out["id"], "md")
    text = md.decode()
    for needle in (
        "## 定稿脚本",
        "旁白全文",
        "## 分镜表",
        "开场／数字",
        "几何色块",
        "## 风格规范",
        "## 素材清单",
        "参考海报（授权：reference_only）",
        "## 交付要求",
        "9:16",
        "Claude Code",
    ):
        assert needle in text, needle
    data, media, name = await os_.bundle(db, out["id"], "zip")
    assert name.endswith(".zip")
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = set(zf.namelist())
    assert {"README.md", "script.md", "storyboard.csv", "style.json"} <= names
    assert any(n.startswith("assets/") and n.endswith("a.png") for n in names)
    assert "先看一个数字" in zf.read("storyboard.csv").decode("utf-8-sig")
    assert (await ps.output_view(db, out["id"]))["status"] == "exported"


def test_short_video_platforms_hook_and_export():
    raw = {
        "title": "标题",
        "hook": "这是一个超过二十个字的开头钩子它太长了必须截掉一些",
        "body": "【画面：桌面】第一句\n【画面：特写】第二句",
        "tags": ["a", "b", "c"],
        "cover_text": "封面",
    }
    issues = {i["field"] for i in rules.check("douyin", raw)}
    assert issues == {"hook"}
    c = os_.normalize_platform("douyin", raw)
    assert len(c["hook"]) == 20 and c["warnings"]
    assert "hook" not in os_.normalize_platform("xhs", raw)
    md, mime = os_.platform_export("douyin", c, "md")
    assert mime == "text/markdown" and "> 开头钩子：" in md and "#a #b #c" in md
    msgs = os_.platform_messages(
        "bilibili", {"draft": {"title": "t", "body": "正文"}}, [{"snapshot": {"title": "A", "url": "https://a"}}]
    )
    assert '"hook"' in msgs[0]["content"] and "B站" in msgs[0]["content"]
