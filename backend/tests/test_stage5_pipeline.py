"""阶段 5：一键全流程（选题研究 → 成稿 →〔定稿〕→ 讲解视频 + 平台改写）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.agent_run import AgentRun, Artifact
from app.models.content import ContentItem, ContentStatus
from app.models.studio import StudioOutput
from app.schemas.projects import ProjectCreate
from app.services import pipeline_service
from app.services import project_service as ps
from app.services.flows import engine

BODY = "第一段：智能体每天花 601 美元。\n\n第二段：任务长度每七个月翻倍。\n\n第三段：结论。"


@pytest_asyncio.fixture
async def env(test_session_factory, monkeypatch, tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    from app.services import trace_payloads

    monkeypatch.setattr(engine, "SESSION_FACTORY", test_session_factory)
    engine.set_checkpointer(InMemorySaver())
    monkeypatch.setattr(trace_payloads, "TRACE_ROOT", tmp_path / "traces")
    monkeypatch.setattr(pipeline_service, "NOTIFY", False)
    async with test_session_factory() as db:
        c = ContentItem(
            title="METR：任务长度翻倍",
            url="https://ex.com/metr",
            status=ContentStatus.PENDING,
            platform="hn",
            summary="编码智能体能完成的任务长度每七个月翻倍",
            crawled_at=datetime.now(UTC),
        )
        db.add(c)
        await db.commit()
        cid = c.id
    yield {"factory": test_session_factory, "content_id": cid}
    engine.set_checkpointer(None)


class FakeLLM:
    def __init__(self, content_id: int):
        self.content_id = content_id
        self.calls: list[str] = []

    async def __call__(self, messages, **kw):
        scene = kw["scene"]
        self.calls.append(scene)
        if scene == "flow_researcher":
            return {
                "action": "final",
                "summary": "有实测",
                "findings": [{"claim": "任务长度七个月翻倍", "sources": [{"type": "content", "id": self.content_id}]}],
            }
        if scene == "flow_aggregator":
            return {"summary": "值得做", "findings": [{"claim": "翻倍曲线", "refs": ["b1.f1"]}]}
        if scene == "flow_planner":
            return {
                "cards": [
                    {"title": "每天 601 美元的智能体", "angle": "算账", "why_now": "新数据", "refs": ["f1"]},
                    {"title": "智能体会取代谁", "angle": "观点", "refs": ["f1"]},
                ]
            }
        if scene == "flow_writer":
            return {"title": "每天 601 美元", "logline": "算账", "body": BODY, "shots": [], "cues": [], "summary": "初稿"}
        if scene == "flow_reviewer":
            return {"summary": "可用", "issues": []}
        if scene == "studio_platform":
            return {"title": "601 美元", "body": "智能体每天 601 美元。", "tags": ["AI", "编程", "效率"]}
        raise AssertionError(scene)


@pytest.fixture
def fake_llm(env, monkeypatch):
    from app.services.llm import provider

    fake = FakeLLM(env["content_id"])
    monkeypatch.setattr(provider, "call_llm_json", fake)
    return fake


async def _pipeline(db, pid):
    project = await ps.get_project(db, pid)
    await db.refresh(project)
    return pipeline_service.view(project.spec)


@pytest.mark.asyncio
async def test_pipeline_runs_to_finalize_then_produces(env, fake_llm):
    async with env["factory"]() as db:
        p = await ps.create_project(db, 1, ProjectCreate(theme="编码智能体", sources=[f"content:{env['content_id']}"]))
        pid = p["id"]
        res = await pipeline_service.start(db, pid, outputs=["video", "xhs"], choose_gate=True, accept_gate=False)
        assert res["stage"] == "research"
        research_id = res["runs"]["research"]
        await engine.wait_run(research_id)
        run = await db.get(AgentRun, research_id, populate_existing=True)
        assert run.status == "waiting"  # 停在选方向关卡
        # 重复启动不另起
        assert (await pipeline_service.start(db, pid))["runs"]["research"] == research_id

        cards = (
            await db.execute(select(Artifact).where(Artifact.run_id == research_id, Artifact.kind == "direction_cards"))
        ).scalar_one()
        second = cards.content["cards"][1]
        await engine.resume_gate(db, research_id, {"card_id": second["id"]})
        await engine.wait_run(research_id)
        pl = await _pipeline(db, pid)
        assert pl["stage"] == "draft", pl
        assert pl["direction"]["title"] == "智能体会取代谁"
        project = await ps.get_project(db, pid)
        await db.refresh(project)
        assert project.spec["brief"]["theme"] == "智能体会取代谁"

        await engine.wait_run(pl["runs"]["draft"])
        pl = await _pipeline(db, pid)
        assert pl["stage"] == "awaiting_finalize", pl
        assert (await ps.draft_view(db, pid))["draft"]["body"].startswith("第一段")

        # 定稿 → 讲解视频（沙箱没有执行者，启动前检查不过，记为问题）+ 平台改写
        await ps.finalize(db, pid)
        pl = await _pipeline(db, pid)
        assert pl["stage"] == "producing", pl
        assert pl["problems"] and "讲解视频" in pl["problems"][0]
        await engine.wait_run(pl["runs"]["platforms"])
        pl = await _pipeline(db, pid)
        assert pl["stage"] == "done" and pl["partial"] is True, pl
        kinds = {
            o.kind
            for o in (await db.execute(select(StudioOutput).where(StudioOutput.project_id == pid))).scalars().all()
        }
        assert "xhs" in kinds


@pytest.mark.asyncio
async def test_pipeline_without_gates_and_stop(env, fake_llm):
    async with env["factory"]() as db:
        p = await ps.create_project(db, 1, ProjectCreate(theme="编码智能体", sources=[f"content:{env['content_id']}"]))
        pid = p["id"]
        res = await pipeline_service.start(db, pid, outputs=["xhs"], choose_gate=False, accept_gate=False)
        await engine.wait_run(res["runs"]["research"])
        pl = await _pipeline(db, pid)
        assert pl["direction"]["title"] == "每天 601 美元的智能体"  # 关卡关闭取第一张
        await engine.wait_run(pl["runs"]["draft"])
        assert (await _pipeline(db, pid))["stage"] == "awaiting_finalize"
        stopped = await pipeline_service.stop(db, pid)
        assert stopped["stage"] == "stopped"
        await ps.finalize(db, pid)  # 已停止：定稿不再触发制作
        assert (await _pipeline(db, pid))["stage"] == "stopped"
