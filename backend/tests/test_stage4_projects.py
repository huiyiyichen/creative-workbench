"""阶段 4：项目、来源快照、工作副本 / 版本 / 定稿、产出物制作层、情绪板。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.exceptions import AppException, ValidationError
from app.models.content import ContentItem, ContentStatus
from app.models.library import LibraryItem
from app.schemas.projects import (
    AssetAdd,
    BriefSave,
    CopyBrief,
    DraftSave,
    OutputCreate,
    OutputPatch,
    ProjectCreate,
    SourceAdd,
)
from app.schemas.studio import StudioDraft
from app.services import project_service as svc


async def _content(db, n: int = 0) -> ContentItem:
    c = ContentItem(
        title=f"来源{n}",
        url=f"https://ex.com/{n}",
        status=ContentStatus.PENDING,
        crawled_at=datetime.now(UTC),
        platform="bilibili",
    )
    db.add(c)
    await db.flush()
    return c


async def _project(db, **kw) -> dict:
    return await svc.create_project(
        db, 1, ProjectCreate(theme=kw.get("theme", "编码智能体"), mode=kw.get("mode", "article"))
    )


def test_paragraph_ids_stable_and_unique():
    ids = svc.paragraph_ids(["甲", "乙", "甲"])
    assert ids[0].startswith("p_") and len(ids[0]) == 10
    assert ids[2] == ids[0] + "_2"
    assert svc.paragraph_ids(["甲"]) == ids[:1]


def test_copy_layer_changed_ignores_production_fields():
    old = {"theme": "a", "mode": "animation_video", "style_id": "x", "aspect_ratio": "16:9"}
    assert not svc.copy_layer_changed(old, {**old, "style_id": "y", "aspect_ratio": "9:16"}, None, None)
    assert svc.copy_layer_changed(old, {**old, "audience": "学生"}, None, None)
    assert svc.copy_layer_changed(old, old, {"body": "一"}, {"body": "二"})


@pytest.mark.asyncio
async def test_create_with_sources_snapshot_and_roles(db):
    c1, c2 = await _content(db, 1), await _content(db, 2)
    lib = LibraryItem(kind="article", title="收藏", url="https://lib")
    db.add(lib)
    await db.commit()
    p = await svc.create_project(db, 1, ProjectCreate(sources=[f"content:{c1.id}", f"library:{lib.id}"]))
    assert p["title"] == "来源1"  # 无主题时取主来源标题
    roles = {s["ref"]: s["role"] for s in p["sources"]}
    assert roles == {f"content:{c1.id}": "main", f"library:{lib.id}": "reference"}
    # 快照冻结：原内容改名不影响
    c1.title = "改过的标题"
    await db.commit()
    assert (await svc.list_sources(db, p["id"]))[0]["snapshot"]["title"] == "来源1"
    # 新主来源会把原主来源降为参考
    await svc.add_source(db, p["id"], SourceAdd(content_id=c2.id, role="main"))
    srcs = await svc.list_sources(db, p["id"])
    assert srcs[0]["content_id"] == c2.id and srcs[0]["role"] == "main"
    assert sum(1 for s in srcs if s["role"] == "main") == 1


@pytest.mark.asyncio
async def test_reference_limit(db):
    p = await _project(db)
    for i in range(9):
        c = await _content(db, 10 + i)
        await svc.add_source(db, p["id"], SourceAdd(content_id=c.id))
    c = await _content(db, 99)
    with pytest.raises(ValidationError):
        await svc.add_source(db, p["id"], SourceAdd(content_id=c.id))


@pytest.mark.asyncio
async def test_autosave_no_version_and_conflict(db):
    p = await _project(db)
    d = await svc.draft_view(db, p["id"])
    t0 = d["draft_token"]
    r = await svc.save_draft(
        db, p["id"], DraftSave(draft=StudioDraft(title="t", body="第一段\n\n第二段"), draft_token=t0)
    )
    assert r["version"] == 0 and r["draft_token"] != t0
    assert (await svc.list_versions(db, p["id"]))["items"] == []
    view = await svc.draft_view(db, p["id"])
    assert [x["text"] for x in view["paragraphs"]] == ["第一段", "第二段"] and view["dirty"]
    # 旧 token 再保存 → 409 draft_conflict
    with pytest.raises(AppException) as e:
        await svc.save_draft(db, p["id"], DraftSave(draft=StudioDraft(body="别处"), draft_token=t0))
    assert e.value.status_code == 409 and e.value.detail["code"] == "draft_conflict"
    # 用我的覆盖：先把对方存成版本
    await svc.save_draft(db, p["id"], DraftSave(draft=StudioDraft(body="我的"), draft_token=t0, force=True))
    versions = (await svc.list_versions(db, p["id"]))["items"]
    assert [v["reason"] for v in versions] == ["overwritten"]
    assert (await svc.version_view(db, p["id"], 1))["draft"]["body"] == "第一段\n\n第二段"


@pytest.mark.asyncio
async def test_finalize_production_settings_do_not_unlock(db):
    p = await _project(db, mode="animation_video")
    pid = p["id"]
    with pytest.raises(AppException) as e:
        await svc.create_output(db, pid, OutputCreate(kind="video"))
    assert e.value.detail["code"] == "not_finalized"
    xhs = await svc.create_output(db, pid, OutputCreate(kind="xhs"))  # 平台版草稿可先建
    assert xhs["can_start"]
    d = await svc.draft_view(db, pid)
    await svc.save_draft(db, pid, DraftSave(draft=StudioDraft(body="成稿"), draft_token=d["draft_token"]))
    fin = await svc.finalize(db, pid)
    assert fin["finalized_version"] == 1 and fin["status"] == "finalized" and fin["stage"] == "outputs"
    out = await svc.create_output(db, pid, OutputCreate(kind="video"))
    assert out["based_on_version"] == 1 and out["settings"]["aspect_ratio"] == "16:9"
    await svc.patch_output(db, out["id"], OutputPatch(settings={"style_id": "bauhaus", "aspect_ratio": "9:16"}))
    assert (await svc.project_view(db, pid))["finalized_version"] == 1  # 改制作参数不撤销定稿
    # 已定稿：改文案层 409，自动保存 409
    brief = CopyBrief(theme="编码智能体", mode="animation_video", audience="程序员")
    with pytest.raises(AppException) as e:
        await svc.save_brief(db, pid, BriefSave(brief=brief))
    assert e.value.detail["code"] == "finalized"
    with pytest.raises(AppException):
        await svc.save_draft(db, pid, DraftSave(draft=StudioDraft(body="改")))
    # 文案层不变的设定保存可以（例如只存方向卡）
    await svc.save_brief(
        db, pid, BriefSave(brief=CopyBrief(theme="编码智能体", mode="animation_video"), idea={"cards": []})
    )
    # 解锁 → 改 → 再定稿 v2；旧产出物提示「文稿已更新」
    await svc.unlock(db, pid)
    await svc.save_brief(db, pid, BriefSave(brief=brief))
    await svc.finalize(db, pid)
    outs = (await svc.list_outputs(db, pid))["items"]
    video = next(o for o in outs if o["kind"] == "video")
    assert video["stale"] and video["latest_finalized"] == 2


@pytest.mark.asyncio
async def test_finalize_requires_content_and_restore_makes_version(db):
    p = await _project(db)
    with pytest.raises(ValidationError):
        await svc.finalize(db, p["id"])
    await svc.save_draft(db, p["id"], DraftSave(draft=StudioDraft(body="一")))
    await svc.create_version(db, p["id"], "manual")
    await svc.save_draft(db, p["id"], DraftSave(draft=StudioDraft(body="二")))
    r = await svc.restore_version(db, p["id"], 1)
    assert r["version"] == 2
    assert (await svc.draft_view(db, p["id"]))["draft"]["body"] == "一"


@pytest.mark.asyncio
async def test_template_generate_and_moodboard(db):
    p = await _project(db, mode="animation_video")
    view = await svc.generate_draft(db, p["id"], "template")
    assert view["version"] == 1 and view["draft"]["shots"]
    assert (await svc.list_versions(db, p["id"]))["items"][0]["reason"] == "compiled"
    item = LibraryItem(kind="image", title="海报")
    db.add(item)
    await db.commit()
    a = await svc.add_asset(db, p["id"], AssetAdd(library_item_id=item.id))
    again = await svc.add_asset(db, p["id"], AssetAdd(library_item_id=item.id))
    assert a["id"] == again["id"]
    assert (await svc.list_assets(db, p["id"], "moodboard"))["items"][0]["item"]["title"] == "海报"
    await svc.remove_asset(db, p["id"], a["id"])
    assert (await svc.list_assets(db, p["id"]))["items"] == []


@pytest.mark.asyncio
async def test_publish_url_sets_status(db):
    p = await _project(db)
    out = await svc.create_output(db, p["id"], OutputCreate(kind="zhihu"))
    r = await svc.patch_output(db, out["id"], OutputPatch(published_url="https://zhuanlan.zhihu.com/p/1"))
    assert r["status"] == "published" and r["published_at"]
    with pytest.raises(ValidationError):
        await svc.patch_output(db, out["id"], OutputPatch(published_url="javascript:alert(1)"))
