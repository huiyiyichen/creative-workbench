"""阶段 5：视频生成接口（异步厂商任务：提交 → 轮询 → 下载；重启续跑；存入并使用）。"""

from __future__ import annotations

import io
import json

import httpx
import pytest
import pytest_asyncio
from PIL import Image

from app.core.exceptions import AppException, ValidationError
from app.models.generation import GenerationJob
from app.models.library import LibraryItem
from app.schemas.projects import ProjectCreate
from app.services import (
    generation_service as gen,
    library,
    library_files,
    project_service as ps,
    task_service,
    video_generation as vg,
)


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), (20, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


class FakeVendor:
    """模拟厂商：提交后前两次轮询在跑，第三次完成。"""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.submits: list[dict] = []
        self.polls = 0

    async def submit(self, service, key, *, prompt, seconds, size, first_frame):
        self.submits.append(
            {
                "prompt": prompt,
                "seconds": seconds,
                "size": size,
                "frame": first_frame.name if first_frame else None,
                "key": key,
            }
        )
        return vg.Submitted(task_id="vid_123")

    async def poll(self, service, key, *, task_id):
        self.polls += 1
        if self.fail:
            return vg.Polled(status="failed", error="内容审核未通过")
        if self.polls < 3:
            return vg.Polled(status="running", progress=self.polls * 30)
        return vg.Polled(status="done", progress=100, data=b"\x00\x00\x00\x18ftypmp42" + b"v" * 100)


@pytest_asyncio.fixture
async def venv(test_session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(gen, "SESSION_FACTORY", test_session_factory)
    monkeypatch.setattr(gen, "GEN_ROOT", tmp_path / "gen")
    monkeypatch.setattr(library_files, "LIBRARY_ROOT", tmp_path / "library")
    monkeypatch.setattr(vg, "POLL_SECONDS", 0)
    fake = FakeVendor()
    monkeypatch.setitem(vg.ADAPTERS, "openai_videos", vg.VideoAdapter(submit=fake.submit, poll=fake.poll))
    return {"factory": test_session_factory, "fake": fake}


async def _service(db, **kw):
    return await gen.save_service(
        db,
        {
            "name": "Sora",
            "kind": "video",
            "api_format": "openai_videos",
            "base_url": "https://video.example.com/v1",
            "model": "sora-2",
            "api_key": "sk-video-9999",
            "unit_price": 0.5,
            "capabilities": {"durations": [4, 8, 12]},
            "is_default": True,
            **kw,
        },
    )


@pytest.mark.asyncio
async def test_video_job_submit_poll_download_keep(venv):
    fake = venv["fake"]
    async with venv["factory"]() as db:
        await _service(db)
        p = await ps.create_project(db, 1, ProjectCreate(theme="视频生成"))
        frame = await library.add_file(db, png(), "frame.png", mime="image/png", method="upload", title="首帧")
        await db.commit()
        with pytest.raises(ValidationError):
            await vg.create_video_job(db, prompt="x", duration=5)  # 不支持的时长
        job = await vg.create_video_job(
            db,
            prompt="镜头缓慢推进到终端屏幕",
            first_frame_item_id=frame.id,
            duration=8,
            aspect="9:16",
            project_id=p["id"],
            target={"type": "shot", "shot": 2},
        )
        assert job.kind == "video" and job.params["estimate"] == 4.0 and job.params["size"] == "720x1280"
        await vg.wait_job(job.id)
        await db.refresh(job)
        assert job.status == "done", job.error
        assert (
            fake.submits[0]["frame"] and fake.submits[0]["seconds"] == 8 and fake.submits[0]["key"] == "sk-video-9999"
        )
        assert fake.polls == 3 and job.cost == 4.0 and job.params["vendor_task_id"] == "vid_123"
        view = gen.job_dict(job)
        assert view["progress"] == 100 and view["results"][0]["url"].endswith("/files/0")
        assert gen.job_file(job, 0).suffix == ".mp4"
        # 任务中心显示为生成视频
        rows = (await task_service.list_tasks(db, types=["generation"]))["items"]
        assert rows[0]["kind_label"] == "生成视频" and rows[0]["status"] == "done"
        # 存入并使用：灵感库视频 + 项目素材挂到第 2 镜
        res = await gen.keep(db, job.id, [0])
        item = await db.get(LibraryItem, res["library_item_ids"][0])
        assert item.meta["params"]["seconds"] == 8 and (item.file_name or "").endswith(".mp4")
        assert res["assets"][0]["role"] == "keyframe"


@pytest.mark.asyncio
async def test_video_job_failure_budget_and_resume(venv, monkeypatch):
    async with venv["factory"]() as db:
        s = await _service(db, daily_limit=5.0)
        with pytest.raises(AppException):
            await vg.create_video_job(db, prompt="太贵", duration=12)  # 0.5 × 12 = 6 > 5
        failing = FakeVendor(fail=True)
        monkeypatch.setitem(vg.ADAPTERS, "openai_videos", vg.VideoAdapter(submit=failing.submit, poll=failing.poll))
        job = await vg.create_video_job(db, prompt="会失败", duration=4)
        await vg.wait_job(job.id)
        await db.refresh(job)
        assert job.status == "failed" and job.error == "内容审核未通过" and job.cost == 0
        row = next(r for r in (await task_service.list_tasks(db))["items"] if r["key"] == f"generation:{job.id}")
        assert row["status"] == "failed" and row["hint"]

        # 重启续跑：已提交的接着轮询，未提交的标失败
        ok = FakeVendor()
        monkeypatch.setitem(vg.ADAPTERS, "openai_videos", vg.VideoAdapter(submit=ok.submit, poll=ok.poll))
        a = GenerationJob(
            kind="video",
            service_id=s["id"],
            prompt="已提交",
            status="running",
            params={"seconds": 4, "vendor_task_id": "vid_9", "submitted_at": "2099-01-01T00:00:00+00:00"},
            results=[],
        )
        b = GenerationJob(
            kind="video", service_id=s["id"], prompt="没提交", status="queued", params={"seconds": 4}, results=[]
        )
        db.add_all([a, b])
        await db.commit()
        assert await vg.resume_pending() == 1
        await vg.wait_job(a.id)
        await db.refresh(a)
        await db.refresh(b)
        assert a.status == "done" and ok.submits == []  # 不重复提交
        assert b.status == "failed" and "重新生成" in b.error


@pytest.mark.asyncio
async def test_openai_videos_adapter_http(monkeypatch):
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}")
        if req.method == "POST":
            assert req.headers["authorization"] == "Bearer k"
            body = json.loads(req.content)
            assert body["model"] == "sora-2" and body["seconds"] == "4" and body["size"] == "1280x720"
            return httpx.Response(200, json={"id": "video_1", "status": "queued"})
        if req.url.path.endswith("/content"):
            return httpx.Response(200, content=b"mp4")
        state = {"n": len([c for c in calls if c == "GET /v1/videos/video_1"])}
        return httpx.Response(
            200, json={"id": "video_1", "status": "completed" if state["n"] > 1 else "in_progress", "progress": 40}
        )

    real = httpx.AsyncClient
    monkeypatch.setattr(vg.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    class S:
        base_url = "https://api.example.com/v1"
        model = "sora-2"

    sub = await vg._openai_submit(S(), "k", prompt="p", seconds=4, size="1280x720", first_frame=None)
    assert sub.task_id == "video_1"
    first = await vg._openai_poll(S(), "k", task_id="video_1")
    assert first.status == "running" and first.progress == 40
    done = await vg._openai_poll(S(), "k", task_id="video_1")
    assert done.status == "done" and done.data == b"mp4"
