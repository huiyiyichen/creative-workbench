"""阶段 5：平台改写流程（平台编辑按平台并行 → 规则校验，写入平台版本产出物）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.models.agent_run import AgentRun, AgentStep, Artifact
from app.models.content import ContentItem, ContentStatus
from app.models.studio import StudioOutput
from app.schemas.projects import OutputCreate, ProjectCreate
from app.schemas.studio import StudioDraft
from app.services import platform_flow, project_service as ps
from app.services.flows import engine
from app.services.flows.spec import load_spec

BODY = "第一段：智能体每天花 601 美元。\n\n第二段：任务长度每七个月翻倍。\n\n第三段：结论。"


@pytest_asyncio.fixture
async def env(test_session_factory, monkeypatch, tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    from app.services import trace_payloads

    monkeypatch.setattr(engine, "SESSION_FACTORY", test_session_factory)
    engine.set_checkpointer(InMemorySaver())
    monkeypatch.setattr(trace_payloads, "TRACE_ROOT", tmp_path / "traces")
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
    """小红书第一次标题超长 → 带问题重写；知乎正常；公众号带违规标签。"""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, messages, **kw):
        assert kw["scene"] == "studio_platform"
        system = messages[0]["content"]
        if "小红书编辑" in system:
            retry = len(messages) > 2
            self.calls.append(("xhs", "retry" if retry else "first"))
            title = "每天 601 美元" if retry else "这是一个明显超过二十个字的小红书标题会被平台拒绝的那种"
            return {"title": title, "body": "姐妹们，智能体每天 601 美元！", "tags": ["AI", "编程", "效率"]}
        if "知乎编辑" in system:
            self.calls.append(("zhihu", "first"))
            return {"title": "编码智能体的翻倍曲线", "body": "## 现状\n\n智能体每天花 601 美元。"}
        if "公众号编辑" in system:
            self.calls.append(("wechat", "first"))
            return {
                "title": "智能体的账单",
                "summary": "一天 601 美元",
                "body": "<p>正文</p><script>alert(1)</script><div>块</div>",
            }
        raise AssertionError(system[:40])


@pytest.fixture
def fake_llm(env, monkeypatch):
    from app.services.llm import provider

    fake = FakeLLM()
    monkeypatch.setattr(provider, "call_llm_json", fake)
    return fake


async def _project_with_draft(db, env) -> int:
    p = await ps.create_project(
        db, 1, ProjectCreate(theme="编码智能体的翻倍曲线", sources=[f"content:{env['content_id']}"])
    )
    await ps.write_draft_version(db, p["id"], StudioDraft(title="每天 601 美元", body=BODY), "manual")
    return p["id"]


def test_platform_rewrite_spec():
    spec = load_spec("platform_rewrite")
    assert [n.id for n in spec.nodes] == ["edit", "check"]
    assert spec.node("edit").parallel == "platforms" and spec.node("check").after == ["edit"]


@pytest.mark.asyncio
async def test_platform_rewrite_parallel_check_and_write_outputs(env, fake_llm):
    async with env["factory"]() as db:
        pid = await _project_with_draft(db, env)
        existing = await ps.create_output(db, pid, OutputCreate(kind="zhihu"))
        res = await platform_flow.start_platform_rewrite(
            db, pid, ["xhs", "zhihu", "wechat", "xhs"], {"zhihu": existing["id"]}
        )
        # 运行中重复点击复用同一运行
        again = await platform_flow.start_platform_rewrite(db, pid, ["xhs"])
        assert again["run_id"] == res["run_id"]
        await engine.wait_run(res["run_id"])
        run = await db.get(AgentRun, res["run_id"], populate_existing=True)
        assert run.status == "done", run.status_reason
        assert sorted(fake_llm.calls) == [("wechat", "first"), ("xhs", "first"), ("xhs", "retry"), ("zhihu", "first")]

        steps = (
            (await db.execute(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.id)))
            .scalars()
            .all()
        )
        edits = [s for s in steps if s.node == "edit"]
        assert sorted(s.branch for s in edits) == ["wechat", "xhs", "zhihu"]
        check = next(s for s in steps if s.node == "check")
        assert len(check.input_artifact_ids) == 3

        outs = (
            (await db.execute(select(StudioOutput).where(StudioOutput.project_id == pid).order_by(StudioOutput.id)))
            .scalars()
            .all()
        )
        by_kind = {o.kind: o for o in outs}
        assert set(by_kind) == {"xhs", "zhihu", "wechat"} and len(outs) == 3
        assert by_kind["zhihu"].id == existing["id"]  # 写进指定的产出物
        assert by_kind["xhs"].content["title"] == "每天 601 美元"
        assert "METR" in by_kind["zhihu"].content["body"]  # 知乎文末补来源
        assert "<script>" not in by_kind["wechat"].content["body"]
        assert by_kind["xhs"].content["run_id"] == run.id

        report = (
            (await db.execute(select(Artifact).where(Artifact.run_id == run.id, Artifact.kind == "platform_check")))
            .scalars()
            .one()
        )
        results = {r["kind"]: r for r in report.content["results"]}
        assert set(results) == {"xhs", "zhihu", "wechat"}
        assert results["xhs"]["output_id"] == by_kind["xhs"].id
        project = await ps.get_project(db, pid)
        assert project.spec["platform_rewrite"]["status"] == "done"


@pytest.mark.asyncio
async def test_platform_rewrite_requires_body_and_platform(env, fake_llm):
    async with env["factory"]() as db:
        p = await ps.create_project(db, 1, ProjectCreate(theme="空稿"))
        with pytest.raises(ValidationError):
            await platform_flow.start_platform_rewrite(db, p["id"], ["xhs"])
        pid = await _project_with_draft(db, env)
        with pytest.raises(ValidationError):
            await platform_flow.start_platform_rewrite(db, pid, ["weibo"])
