"""阶段 4 第 ④ 步：生成服务与用灵感生图（候选、存入并使用、每日上限、参考图、关键帧）。"""

from __future__ import annotations

import io
import os
import time
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.core.exceptions import AppException, ValidationError
from app.models.generation import GenerationJob
from app.models.library import LibraryItem, LibraryLink
from app.models.project import ProjectAsset
from app.schemas.projects import AssetAdd, ProjectCreate
from app.services import generation_service as gen, library_files, project_service as ps


def png(color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, "PNG")
    return buf.getvalue()


class FakeAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, service, key, *, prompt, size, n, refs):
        self.calls.append({"key": key, "prompt": prompt, "size": size, "n": n, "refs": [p.name for p in refs]})
        return [png((10 * i, 100, 200)) for i in range(n)]


@pytest_asyncio.fixture
async def genv(test_session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(gen, "SESSION_FACTORY", test_session_factory)
    monkeypatch.setattr(gen, "GEN_ROOT", tmp_path / "gen")
    monkeypatch.setattr(library_files, "LIBRARY_ROOT", tmp_path / "library")
    fake = FakeAdapter()
    monkeypatch.setitem(gen.ADAPTERS, "openai_images", fake)
    return {"factory": test_session_factory, "fake": fake, "tmp": tmp_path}


async def _service(db, **kw):
    values = {
        "name": "image2.5",
        "base_url": "https://img.example.com/v1/",
        "model": "image-2.5",
        "api_key": "sk-secret-abcd1234",
        "unit_price": 0.2,
        "capabilities": {"refs": True, "max_n": 4},
        "is_default": True,
        **kw,
    }
    return await gen.save_service(db, values)


@pytest.mark.asyncio
async def test_service_key_encrypted_and_masked(genv):
    async with genv["factory"]() as db:
        s = await _service(db)
        assert s["key_hint"] == "…1234" and s["base_url"] == "https://img.example.com/v1"
        assert "sk-secret" not in str(s)
        assert await gen.available(db)
        s2 = await gen.save_service(db, {"daily_limit": 1.0}, s["id"])
        assert s2["daily_limit"] == 1.0 and s2["has_key"]
        s3 = await gen.save_service(db, {"daily_limit": None}, s["id"])
        assert s3["daily_limit"] is None
        with pytest.raises(ValidationError):
            await gen.save_service(db, {"name": "x", "base_url": "ftp://x", "model": "m"})


@pytest.mark.asyncio
async def test_moodboard_refs_generate_keep_into_library_and_project(genv):
    fake = genv["fake"]
    async with genv["factory"]() as db:
        await _service(db)
        p = await ps.create_project(db, 1, ProjectCreate(theme="601 美元"))
        refs = []
        for i in range(2):
            item = await __import__("app.services.library", fromlist=["add_file"]).add_file(
                db, png((i * 90, 20, 20)), f"poster{i}.png", mime="image/png"
            )
            refs.append(item.id)
            await ps.add_asset(db, p["id"], AssetAdd(library_item_id=item.id, role="moodboard"))
        job = await gen.create_job(
            db,
            prompt="几何色块构成的时间轴",
            ref_item_ids=refs,
            n=6,  # 服务最多 4 张
            project_id=p["id"],
            target={"type": "xhs", "index": 2},
        )
        await gen.wait_job(job.id)
        view = await gen.get_job(db, job.id)
        assert view["status"] == "done" and len(view["results"]) == 4
        assert view["params"]["aspect"] == "3:4" and view["params"]["size"] == "1024x1536"
        assert view["cost"] == pytest.approx(0.8)
        assert fake.calls[0]["key"] == "sk-secret-abcd1234" and len(fake.calls[0]["refs"]) == 2
        res = await gen.keep(db, job.id, [1])
        lib = await db.get(LibraryItem, res["library_item_ids"][0])
        assert lib.kind == "generated" and lib.license == "ai"
        assert lib.meta["prompt"] == "几何色块构成的时间轴" and lib.meta["ref_item_ids"] == refs
        assert lib.meta["model"] == "image-2.5"
        links = (await db.execute(select(LibraryLink).where(LibraryLink.to_id == lib.id))).scalars().all()
        assert {ln.from_id for ln in links} == set(refs) and all(ln.relation == "generated" for ln in links)
        asset = (
            await db.execute(select(ProjectAsset).where(ProjectAsset.library_item_id == lib.id))
        ).scalar_one()
        assert asset.role == "illustration" and asset.target == {"index": 2}
        # 以此为参考再生成：选中的图成为第一张参考
        job2 = await gen.create_job(db, prompt="出变体", parent_job_id=job.id, parent_index=1, n=2)
        assert job2.ref_item_ids[0] == lib.id
        await gen.wait_job(job2.id)
        assert fake.calls[-1]["n"] == 2


@pytest.mark.asyncio
async def test_no_ref_support_puts_descriptions_in_prompt(genv):
    fake = genv["fake"]
    async with genv["factory"]() as db:
        await _service(db, capabilities={"refs": False})
        item = LibraryItem(kind="prompt", title="包豪斯海报", body="红黄蓝几何、粗无衬线")
        db.add(item)
        await db.commit()
        job = await gen.create_job(db, prompt="封面", ref_item_ids=[item.id], n=1, launch=False)
        await gen.run_job(db, job.id)
        assert fake.calls[0]["refs"] == [] and "红黄蓝几何" in fake.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_daily_limit_and_not_configured(genv):
    async with genv["factory"]() as db:
        with pytest.raises(AppException) as e:
            await gen.create_job(db, prompt="x", n=1)
        assert e.value.status_code == 503
        await _service(db, daily_limit=1.0)
        job = await gen.create_job(db, prompt="x", n=4, launch=False)
        await gen.run_job(db, job.id)  # 0.8
        with pytest.raises(AppException) as e:
            await gen.create_job(db, prompt="y", n=2)
        assert e.value.status_code == 429 and "每日上限" in e.value.message


@pytest.mark.asyncio
async def test_adapter_failure_marks_failed(genv, monkeypatch):
    async def boom(*a, **kw):
        raise AppException("生成服务返回 500：overloaded", 502)

    monkeypatch.setitem(gen.ADAPTERS, "openai_images", boom)
    async with genv["factory"]() as db:
        await _service(db)
        job = await gen.create_job(db, prompt="x", n=1, launch=False)
        job = await gen.run_job(db, job.id)
        assert job.status == "failed" and "overloaded" in job.error and job.cost == 0
        with pytest.raises(ValidationError):
            await gen.keep(db, job.id, [0])


@pytest.mark.asyncio
async def test_keyframe_for_flow_assigns_shot(genv):
    async with genv["factory"]() as db:
        await _service(db)
        p = await ps.create_project(db, 1, ProjectCreate(theme="t", mode="animation_video"))
        item_id = await gen.keyframe_for_flow(
            db, project_id=p["id"], output_id=7, shot=3, prompt="上升曲线", aspect_ratio="9:16"
        )
        assert item_id
        asset = (await db.execute(select(ProjectAsset).where(ProjectAsset.library_item_id == item_id))).scalar_one()
        assert asset.role == "keyframe" and asset.target == {"shot": 3, "output_id": 7}
        job = (await db.execute(select(GenerationJob))).scalars().one()
        assert job.params["aspect"] == "9:16" and job.params["n"] == 1


def test_cleanup_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "GEN_ROOT", tmp_path)
    old, new = tmp_path / "1", tmp_path / "2"
    old.mkdir()
    new.mkdir()
    past = time.time() - 8 * 86400
    os.utime(old, (past, past))
    assert gen.cleanup_candidates(datetime.now(UTC)) == 1
    assert not old.exists() and new.exists()


@pytest.mark.asyncio
async def test_target_context_reads_shot_and_paragraph(genv):
    from app.schemas.studio import StudioDraft

    async with genv["factory"]() as db:
        p = await ps.create_project(db, 1, ProjectCreate(theme="t", mode="animation_video"))
        await ps.write_draft_version(
            db,
            p["id"],
            StudioDraft(
                title="t",
                body="第一段\n\n第二段",
                shots=[{"seconds": 3, "beat": "钩子", "visual": "数字 601", "prompt": "大字"}],
            ),
            "manual",
        )
        ctx = await gen.target_context(db, p["id"], {"type": "shot", "shot": 1})
        assert "数字 601" in ctx
        pid = ps.paragraphs_with_ids("第一段\n\n第二段")[1]["id"]
        assert "第二段" in await gen.target_context(db, p["id"], {"type": "paragraph", "paragraph_id": pid})
