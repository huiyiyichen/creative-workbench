"""阶段 3：流程引擎（LangGraph）、运行记录与溯源、研究员与选题研究流程、工作台工具与 MCP。"""

from __future__ import annotations

import asyncio
import gzip
import json
import re
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.agent_run import AgentDecision, AgentRun, AgentStep, Artifact, ArtifactLink, TraceSpan
from app.models.content import ContentItem, ContentStatus
from app.models.llm_model import LlmCallLog
from app.services import trace_service, workbench_tools as wt
from app.services.flows import engine
from app.services.flows.spec import FlowSpecError, load_spec, parse_spec


@pytest_asyncio.fixture
async def flow_env(test_session_factory, monkeypatch, tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    from app.services import trace_payloads

    monkeypatch.setattr(engine, "SESSION_FACTORY", test_session_factory)
    engine.set_checkpointer(InMemorySaver())
    monkeypatch.setattr(trace_payloads, "TRACE_ROOT", tmp_path)
    async with test_session_factory() as db:
        c = ContentItem(
            title="Opus 5.5 做 MV 实测",
            url="https://www.bilibili.com/video/BV1aa411c7aa",
            status=ContentStatus.PENDING,
            platform="bilibili",
            platform_item_id="BV1aa411c7aa",
            summary="用 Opus 5.5 生成整支 MV 的流程",
            crawled_at=datetime.now(UTC),
        )
        db.add(c)
        await db.commit()
        cid = c.id
    yield {"content_id": cid, "factory": test_session_factory, "traces": tmp_path}
    engine.set_checkpointer(None)


class FakeLLM:
    """按场景返回脚本化结果；研究员先调一次工具再给结论。"""

    def __init__(self, content_id: int):
        self.content_id = content_id
        self.calls: list[str] = []
        self.fail_planner = 0
        self.hang_researcher = False
        self.planner_prompts: list[str] = []

    async def __call__(self, messages, **kw):
        scene = kw["scene"]
        self.calls.append(scene)
        if scene == "flow_researcher":
            if self.hang_researcher:
                await asyncio.sleep(30)
            if not any(m["role"] == "assistant" for m in messages):
                return {"action": "tool", "tool": "search_content", "args": {"query": "Opus"}, "why": "找素材"}
            return {
                "action": "final",
                "summary": "B站上已有实测",
                "findings": [
                    {
                        "claim": "已有 UP 主用 Opus 5.5 做完整 MV",
                        "sources": [{"type": "content", "id": self.content_id}],
                    },
                    {"claim": "没有出处的结论", "sources": []},
                    {"claim": "编造的出处", "sources": [{"type": "content", "id": 99999}]},
                ],
            }
        if scene == "flow_aggregator":
            refs = re.findall(r"\[(b\d+\.f\d+)\]", messages[1]["content"])
            return {"summary": "值得做", "findings": [{"claim": "已有实测，但缺教程", "refs": refs[:2] + ["b0.f9"]}]}
        if scene == "flow_planner":
            self.planner_prompts.append(messages[0]["content"])
            if self.fail_planner > 0:
                self.fail_planner -= 1
                raise RuntimeError("模型超时")
            return {
                "cards": [
                    {
                        "title": "手把手做一支 AI MV",
                        "angle": "教程",
                        "why_now": "刚发布",
                        "format": "video",
                        "refs": ["f1"],
                    },
                    {"title": "AI MV 能替代剪辑师吗", "angle": "观点", "why_now": "争议大", "refs": ["f1", "f7"]},
                ]
            }
        raise AssertionError(scene)


@pytest.fixture
def fake_llm(flow_env, monkeypatch):
    from app.services.llm import provider

    fake = FakeLLM(flow_env["content_id"])
    monkeypatch.setattr(provider, "call_llm_json", fake)
    return fake


async def _run(db, **kw):
    inputs = {"topic": "AI 做 MV", "platforms": ["bilibili", "library"], **kw.pop("inputs", {})}
    run = await engine.start_run(db, "topic_research", inputs, **kw)
    await engine.wait_run(run.id)
    await db.refresh(run)
    return run


async def _steps(db, run_id):
    return (
        (
            await db.execute(
                select(AgentStep)
                .where(AgentStep.run_id == run_id)
                .order_by(AgentStep.id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


def test_spec_loads_and_validates():
    spec = load_spec("topic_research")
    assert [n.id for n in spec.nodes] == ["research", "aggregate", "plan", "choose"]
    assert spec.ancestors("plan") == {"research", "aggregate"}
    g = spec.graph_view({"choose": False})
    assert {"from": "plan", "to": "choose"} in g["edges"] and g["nodes"][-1]["enabled"] is False
    with pytest.raises(FlowSpecError):
        parse_spec({"key": "x", "nodes": [{"id": "a", "role": "editor"}]})
    with pytest.raises(FlowSpecError):
        parse_spec({"key": "x", "nodes": [{"id": "a", "role": "planner", "after": ["b"]}]})
    with pytest.raises(FlowSpecError):
        load_spec("../etc")


@pytest.mark.asyncio
async def test_topic_research_gate_and_resume(flow_env, fake_llm):
    async with flow_env["factory"]() as db:
        run = await _run(db)
        assert run.status == "waiting", run.status_reason
        steps = await _steps(db, run.id)
        by = [(s.node, s.branch, s.status) for s in steps]
        assert ("research", "bilibili", "done") in by and ("research", "library", "done") in by
        assert ("aggregate", None, "done") in by and ("plan", None, "done") in by and ("choose", None, "waiting") in by

        # 研究员：只保留带真实出处的结论；工具调用进入调用树
        brief = (
            await db.execute(select(Artifact).where(Artifact.run_id == run.id, Artifact.title == "研究简报 · B站"))
        ).scalar_one()
        assert [f["claim"] for f in brief.content["findings"]] == ["已有 UP 主用 Opus 5.5 做完整 MV"]
        assert brief.content["dropped"] == 2
        spans = (await db.execute(select(TraceSpan).where(TraceSpan.run_id == run.id))).scalars().all()
        assert {s.name for s in spans} == {"search_content"} and len(spans) == 2

        detail = await trace_service.run_detail(db, run.id)
        assert detail["graph"]["nodes"][0]["id"] == "research"
        cards = next(a for a in detail["artifacts"] if a["kind"] == "direction_cards")
        assert cards["content"]["cards"][1]["refs"] == ["f1"]  # 不存在的 f7 被去掉

        # 关卡：非法选择被拒绝；选 d2 后运行完成
        with pytest.raises(engine.FlowError):
            await engine.resume_gate(db, run.id, {"card_id": "d9"})
        await engine.resume_gate(db, run.id, {"card_id": "d2", "note": "更有讨论度"})
        await engine.wait_run(run.id)
        await db.refresh(run)
        assert run.status == "done"
        assert run.outputs["decisions"]["choose"]["title"] == "AI MV 能替代剪辑师吗"
        d = (await db.execute(select(AgentDecision).where(AgentDecision.run_id == run.id))).scalar_one()
        assert d.choice["card_id"] == "d2" and d.note == "更有讨论度" and len(d.options) == 2
        # 关卡节点恢复时重跑不会产生第二个关卡步骤
        assert [s.status for s in await _steps(db, run.id) if s.node == "choose"] == ["done"]
        assert fake_llm.calls.count("flow_planner") == 1


@pytest.mark.asyncio
async def test_gate_disabled_runs_through(flow_env, fake_llm):
    async with flow_env["factory"]() as db:
        run = await _run(db, gates={"choose": False}, inputs={"platforms": ["bilibili"]})
        assert run.status == "done"
        assert run.outputs["decisions"]["choose"] == {"auto": True}
        assert run.graph["nodes"][-1]["enabled"] is False


@pytest.mark.asyncio
async def test_budget_pause_and_continue(flow_env, fake_llm):
    async with flow_env["factory"]() as db:
        run = await _run(db, budget={"steps": 2})
        assert run.status == "paused" and "上限 2 步" in run.status_reason
        assert {s.node for s in await _steps(db, run.id)} == {"research"}
        with pytest.raises(engine.FlowError):
            await engine.resume_gate(db, run.id, {"card_id": "d1"})
        await engine.continue_run(db, run.id, {"steps": 10})
        await engine.wait_run(run.id)
        await db.refresh(run)
        assert run.status == "waiting" and run.budget["steps"] == 12
        # 研究员没有重跑
        assert fake_llm.calls.count("flow_researcher") == 4


@pytest.mark.asyncio
async def test_failure_then_continue_from_failed_step(flow_env, fake_llm):
    fake_llm.fail_planner = 1
    async with flow_env["factory"]() as db:
        run = await _run(db, inputs={"platforms": ["bilibili"]})
        assert run.status == "failed" and "模型超时" in run.status_reason
        plan_steps = [s for s in await _steps(db, run.id) if s.node == "plan"]
        assert plan_steps[0].status == "failed" and plan_steps[0].error == "模型超时"
        await engine.continue_run(db, run.id)
        await engine.wait_run(run.id)
        await db.refresh(run)
        assert run.status == "waiting"
        plan_steps = [s for s in await _steps(db, run.id) if s.node == "plan"]
        assert [(s.status, s.attempt) for s in plan_steps] == [("failed", 1), ("done", 2)]
        assert fake_llm.calls.count("flow_researcher") == 2  # 上游不重跑


@pytest.mark.asyncio
async def test_fork_from_node_reuses_upstream(flow_env, fake_llm):
    async with flow_env["factory"]() as db:
        run = await _run(db)
        with pytest.raises(engine.FlowError):
            await engine.fork_run(db, run.id, "choose")
        fork = await engine.fork_run(db, run.id, "plan", {"prompt_extra": "多给一个盘点类方向", "bogus": "x"})
        await engine.wait_run(fork.id)
        await db.refresh(fork)
        assert fork.status == "waiting" and fork.parent_run_id == run.id and fork.fork_node == "plan"
        steps = await _steps(db, fork.id)
        assert [(s.node, s.status) for s in steps if s.node != "choose"] == [
            ("research", "reused"),
            ("research", "reused"),
            ("aggregate", "reused"),
            ("plan", "done"),
        ]
        assert "多给一个盘点类方向" in fake_llm.planner_prompts[-1]
        assert fake_llm.calls.count("flow_researcher") == 4  # 原运行 2 个分支 × 2 轮，分叉没有再跑
        # 原运行不变；分叉复用原简报
        orig_agg = next(s for s in await _steps(db, run.id) if s.node == "aggregate")
        fork_agg = next(s for s in steps if s.node == "aggregate")
        assert fork_agg.output_artifact_ids == orig_agg.output_artifact_ids
        detail = await trace_service.run_detail(db, run.id)
        assert detail["forks"][0]["id"] == fork.id


@pytest.mark.asyncio
async def test_stop_running(flow_env, fake_llm):
    fake_llm.hang_researcher = True
    async with flow_env["factory"]() as db:
        run = await engine.start_run(db, "topic_research", {"topic": "停止测试", "platforms": ["bilibili"]})
        for _ in range(50):
            await asyncio.sleep(0.05)
            if any(s.status == "running" for s in await _steps(db, run.id)):
                break
        await engine.stop_run(db, run.id)
        await db.refresh(run)
        assert run.status == "stopped"
        assert [s.status for s in await _steps(db, run.id)] == ["stopped"]


@pytest.mark.asyncio
async def test_trace_tree_step_detail_and_lineage(flow_env, fake_llm):
    async with flow_env["factory"]() as db:
        run = await _run(db, inputs={"platforms": ["bilibili"]})
        plan = next(s for s in await _steps(db, run.id) if s.node == "plan")
        db.add(
            LlmCallLog(
                request_id="req-flow-1",
                scene="flow_planner",
                status="DONE",
                input_tokens=1200,
                output_tokens=300,
                total_cost=0.02,
                run_id=str(run.id),
                step_id=str(plan.id),
            )
        )
        await db.commit()
        tree = await trace_service.trace_tree(db, run.id)
        research = tree[0]
        assert research["tool_calls"] == 1 and research["children"][0]["kind"] == "tool"
        plan_node = next(n for n in tree if n["node"] == "plan")
        assert plan_node["llm_calls"] == 1 and plan_node["children"][0]["cost"] == 0.02
        payload = await trace_service.span_payload(db, research["children"][0]["id"])
        assert payload["tool"] == "search_content" and payload["result"][0]["content_id"] == flow_env["content_id"]

        detail = await trace_service.step_detail(db, plan.id)
        assert detail["inputs"][0]["kind"] == "research_brief" and detail["outputs"][0]["kind"] == "direction_cards"

        cards = (await db.execute(select(Artifact).where(Artifact.kind == "direction_cards"))).scalar_one()
        lin = await trace_service.lineage(db, cards.id)
        agg = lin["sources"][0]
        assert agg["kind"] == "research_brief" and agg["title"] == "研究简报 · 汇总"
        branch = next(s for s in agg["sources"] if s.get("title") == "研究简报 · B站")
        assert any(s["type"] == "content" and s["id"] == flow_env["content_id"] for s in branch["sources"])
        cite = next(s for s in lin["sources"] if s["relation"] == "cites")
        assert cite["anchor"] == "d1" and cite["target_anchor"] == "f1"
        assert (await db.execute(select(ArtifactLink))).scalars().first() is not None
        assert (await trace_service.lineage(db, agg["id"]))["used_by"][0]["id"] == cards.id


@pytest.mark.asyncio
async def test_tool_payload_redacted_and_mcp(flow_env, db):
    ctx = wt.ToolContext(run_id=None)
    out = await wt.call_tool(db, "write_note", {"body": "试试 #AI", "api_key": "sk-abcdefghijklmnopqrstuvwx"}, ctx)
    assert out["note_id"]
    files = list(flow_env["traces"].rglob("*.json.gz"))
    assert files and "sk-abcdefghijklmnopqrstuvwx" not in gzip.open(files[0]).read().decode("utf-8")
    with pytest.raises(wt.ToolError):
        await wt.call_tool(db, "nope", {})

    raw, tok = await wt.issue_token(db, "Claude Code", tools=["search_content", "read_content"])
    init = await wt.handle_mcp(db, raw, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "creative-workbench"
    assert await wt.handle_mcp(db, raw, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    listed = await wt.handle_mcp(db, raw, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [t["name"] for t in listed["result"]["tools"]] == ["search_content", "read_content"]
    db.add(
        ContentItem(
            title="MCP 能搜到我",
            url="https://ex.com/mcp",
            status=ContentStatus.PENDING,
            crawled_at=datetime.now(UTC),
        )
    )
    await db.commit()
    called = await wt.handle_mcp(
        db,
        raw,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search_content", "arguments": {"query": "MCP"}},
        },
    )
    assert json.loads(called["result"]["content"][0]["text"])[0]["title"] == "MCP 能搜到我"
    denied = await wt.handle_mcp(
        db, raw, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "write_note", "arguments": {}}}
    )
    assert denied["error"]["code"] == -32001
    bad = await wt.handle_mcp(
        db,
        raw,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "read_content", "arguments": {"content_id": 0}},
        },
    )
    assert bad["result"]["isError"] is True
    span = (await db.execute(select(TraceSpan).where(TraceSpan.via == "mcp").order_by(TraceSpan.id))).scalars().all()
    assert [s.name for s in span] == ["search_content", "read_content"] and span[0].token_id == tok.id

    tok.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    expired = await wt.handle_mcp(db, raw, {"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
    assert expired["error"]["message"] == "令牌已过期"
    assert (await wt.handle_mcp(db, "cw_wrong", {"jsonrpc": "2.0", "id": 7, "method": "ping"}))["error"]
    raw2, tok2 = await wt.issue_token(db, "x")
    assert await wt.revoke_token(db, tok2.id)
    assert (await wt.handle_mcp(db, raw2, {"jsonrpc": "2.0", "id": 8, "method": "ping"}))["error"][
        "message"
    ] == "令牌无效"


@pytest.mark.asyncio
async def test_recover_on_startup(flow_env):
    async with flow_env["factory"]() as db:
        run = AgentRun(flow_key="topic_research", title="x", status="running", thread_id="t1")
        db.add(run)
        await db.commit()
        db.add(AgentStep(run_id=run.id, node="research", role="researcher", label="研究员", status="running"))
        await db.commit()
        assert await engine.recover_on_startup() == 1
        await db.refresh(run)
        assert run.status == "paused" and "服务重启" in run.status_reason
