"""阶段 4 第 ③ 步：成稿流程（写手 → 审校 → 写手修改 →〔接受〕→ 写入文稿）与成片流程
（分镜 → 美术 → 制作 → 质检，不通过退回制作最多 2 次）、外部执行者事件转换。"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import AppException
from app.models.agent_run import AgentRun, AgentStep, Artifact
from app.models.content import ContentItem, ContentStatus
from app.models.studio import StudioArtifact, StudioRevision
from app.schemas.projects import OutputCreate, ProjectCreate
from app.schemas.studio import StudioDraft
from app.services import (
    agent_adapters,
    draft_flow,
    production_service,
    project_lineage,
    project_service as ps,
    trace_service,
)
from app.services.flows import engine
from app.services.flows.spec import FlowSpecError, load_spec, parse_spec

BODY1 = "第一段：智能体每天花 601 美元。\n\n第二段：任务长度每七个月翻倍。\n\n第三段：结论。"
BODY2 = "第一段：智能体每天花 601 美元，相当于一个初级工程师。\n\n第二段：任务长度每七个月翻倍。\n\n第三段：结论更克制。"


@pytest_asyncio.fixture
async def env(test_session_factory, monkeypatch, tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    from app.services import studio_media, trace_payloads

    monkeypatch.setattr(engine, "SESSION_FACTORY", test_session_factory)
    engine.set_checkpointer(InMemorySaver())
    monkeypatch.setattr(trace_payloads, "TRACE_ROOT", tmp_path / "traces")
    monkeypatch.setattr(studio_media, "MEDIA_ROOT", tmp_path / "media")
    monkeypatch.setattr(production_service, "SAVE_WORK", False)

    async def no_problems(db, project, output):
        return []

    monkeypatch.setattr(production_service, "PREFLIGHT", no_problems)
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
    yield {"factory": test_session_factory, "content_id": cid, "tmp": tmp_path}
    engine.set_checkpointer(None)


class FakeLLM:
    def __init__(self):
        self.calls: list[str] = []
        self.issues = [
            {"paragraph": 1, "severity": "high", "problem": "缺少类比", "suggestion": "加一个类比"},
            {"paragraph": 9, "severity": "low", "problem": "不存在的段落", "suggestion": "x"},
            {"paragraph": 3, "severity": "medium", "problem": "结论太满", "suggestion": "收一点"},
        ]
        self.revise_prompts: list[str] = []

    async def __call__(self, messages, **kw):
        scene = kw["scene"]
        self.calls.append(scene)
        if scene == "flow_writer":
            if "修改稿" in messages[0]["content"]:
                self.revise_prompts.append(messages[1]["content"])
                return {
                    "title": "每天 601 美元",
                    "logline": "编码智能体的翻倍曲线",
                    "body": BODY2,
                    "shots": [],
                    "cues": [],
                    "citations": [{"paragraph": 2, "sources": [1]}],
                    "resolved": [{"issue": "r1", "how": "加了类比"}],
                    "summary": "按意见修改",
                }
            return {
                "title": "每天 601 美元",
                "logline": "编码智能体",
                "body": BODY1,
                "shots": [],
                "cues": [],
                "citations": [{"paragraph": 2, "sources": [1, 5]}, {"paragraph": 7, "sources": [1]}],
                "summary": "初稿",
            }
        if scene == "flow_reviewer":
            return {"summary": "整体可用", "issues": self.issues}
        raise AssertionError(scene)


@pytest.fixture
def fake_llm(env, monkeypatch):
    from app.services.llm import provider

    fake = FakeLLM()
    monkeypatch.setattr(provider, "call_llm_json", fake)
    return fake


async def _project(db, env, mode="article") -> int:
    p = await ps.create_project(
        db, 1, ProjectCreate(theme="编码智能体的翻倍曲线", mode=mode, sources=[f"content:{env['content_id']}"])
    )
    return p["id"]


async def _steps(db, run_id):
    stmt = select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.id)
    return (await db.execute(stmt.execution_options(populate_existing=True))).scalars().all()


async def _arts(db, run_id, kind=None):
    stmt = select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.id)
    if kind:
        stmt = stmt.where(Artifact.kind == kind)
    return (await db.execute(stmt)).scalars().all()


# ── 模板 ──


def test_new_specs_and_loop_validation():
    d = load_spec("draft_writing")
    assert [n.id for n in d.nodes] == ["write", "review", "revise", "accept", "apply"]
    assert d.node("revise").reads == ["write"] and d.node("accept").gate["kind"] == "accept"
    v = load_spec("video_production")
    assert v.node("qa").loop_to == "produce" and v.node("qa").max_loops == 2
    assert {"from": "qa", "to": "produce", "loop": True, "max_loops": 2} in v.graph_view()["edges"]
    base = {"key": "x", "nodes": [{"id": "a", "role": "writer"}, {"id": "b", "role": "qa", "after": ["a"]}]}
    with pytest.raises(FlowSpecError):
        parse_spec({**base, "nodes": [base["nodes"][0], {**base["nodes"][1], "loop_to": "a"}]})  # 缺 max_loops
    with pytest.raises(FlowSpecError):
        parse_spec({**base, "nodes": [{**base["nodes"][0], "reads": ["zz"]}, base["nodes"][1]]})
    with pytest.raises(FlowSpecError):
        parse_spec({"key": "x", "nodes": [{"id": "g", "type": "gate", "gate": {"kind": "nope"}}]})


# ── 成稿流程 ──


@pytest.mark.asyncio
async def test_ai_draft_flow_writes_version_with_paragraph_citations(env, fake_llm):
    async with env["factory"]() as db:
        pid = await _project(db, env)
        res = await ps.generate_draft(db, pid, "ai")
        run_id = res["run_id"]
        await engine.wait_run(run_id)
        run = await db.get(AgentRun, run_id, populate_existing=True)
        assert run.status == "done", run.status_reason
        assert fake_llm.calls == ["flow_writer", "flow_reviewer", "flow_writer"]
        # 修改稿看到了原稿与过滤后的意见（不存在的段落不带段落号）
        assert "缺少类比" in fake_llm.revise_prompts[0] and "第一段" in fake_llm.revise_prompts[0]
        steps = await _steps(db, run_id)
        assert [s.node for s in steps] == ["write", "review", "revise", "accept", "apply"]
        assert steps[3].meta.get("auto") is True
        review = (await _arts(db, run_id, "review"))[0]
        assert [i["paragraph"] for i in review.content["issues"]] == [1, None, 3]
        assert review.content["passed"] is False
        # 写成新版本（原因 ai），工作副本是修改稿
        project = await ps.get_project(db, pid)
        assert project.spec["draft"]["body"] == BODY2 and project.spec["draft"]["provenance"] == "ai"
        rev = (
            await db.execute(select(StudioRevision).where(StudioRevision.project_id == pid, StudioRevision.version == project.version))
        ).scalar_one()
        assert rev.reason == "ai"
        assert project.spec["ai_draft"]["status"] == "done"
        # 溯源：文稿版本 → 修改稿 → 采集内容，段落锚点准确
        dv = await project_lineage.find_version_artifact(db, pid, project.version)
        assert dv is not None and dv.content["version"] == project.version
        lin = await trace_service.lineage(db, dv.id)
        p2 = ps.paragraphs_with_ids(BODY2)[1]["id"]
        cites = [s for s in lin["sources"] if s["type"] == "content"]
        assert cites and cites[0]["id"] == env["content_id"] and cites[0]["anchor"] == p2
        drafts = await _arts(db, run_id, "draft")
        first = drafts[0]
        assert first.content["citations"] == [{"paragraph_id": ps.paragraphs_with_ids(BODY1)[1]["id"], "sources": [1]}]


@pytest.mark.asyncio
async def test_ai_draft_gate_reject_keeps_draft(env, fake_llm):
    async with env["factory"]() as db:
        pid = await _project(db, env)
        before = (await ps.get_project(db, pid)).version
        res = await draft_flow.start_ai_draft(db, pid, review_gate=True)
        await engine.wait_run(res["run_id"])
        run = await db.get(AgentRun, res["run_id"], populate_existing=True)
        assert run.status == "waiting"
        gate = (await _steps(db, run.id))[-1]
        assert [o["id"] for o in gate.meta["options"]] == ["accept", "reject"]
        # 等待中再点「AI 写初稿」不另起运行
        again = await draft_flow.start_ai_draft(db, pid, review_gate=True)
        assert again["run_id"] == run.id
        await engine.resume_gate(db, run.id, {"card_id": "reject"})
        await engine.wait_run(run.id)
        run = await db.get(AgentRun, run.id, populate_existing=True)
        assert run.status == "done"
        steps = await _steps(db, run.id)
        assert steps[-1].node == "apply" and steps[-1].meta["summary"] == "未接受，文稿不变"
        assert (await ps.get_project(db, pid)).version == before


@pytest.mark.asyncio
async def test_no_review_issues_skips_revision_model_call(env, fake_llm):
    fake_llm.issues = []
    async with env["factory"]() as db:
        pid = await _project(db, env)
        res = await ps.generate_draft(db, pid, "ai")
        await engine.wait_run(res["run_id"])
        assert fake_llm.calls == ["flow_writer", "flow_reviewer"]
        assert (await ps.get_project(db, pid)).spec["draft"]["body"] == BODY1


@pytest.mark.asyncio
async def test_ai_draft_refused_when_finalized(env, fake_llm):
    async with env["factory"]() as db:
        pid = await _project(db, env)
        await ps.write_draft_version(db, pid, StudioDraft(title="t", body="正文"), "manual")
        await ps.finalize(db, pid)
        with pytest.raises(AppException) as e:
            await ps.generate_draft(db, pid, "ai")
        assert e.value.status_code == 409


# ── 成片流程 ──

SHOTS = [
    {"seconds": 4, "beat": "钩子", "visual": "数字 601", "audio": "每天 601 美元。", "prompt": "大字 601"},
    {"seconds": 6, "beat": "翻倍", "visual": "曲线", "audio": "任务长度每七个月翻倍。", "prompt": "上升曲线"},
]


class FakeProducer:
    def __init__(self):
        self.jobs: list[dict] = []

    async def __call__(self, job: production_service.ProductionJob) -> production_service.ProductionResult:
        await job.stage("配音", 10)
        await job.stage("Remotion 渲染", 60)
        self.jobs.append(
            {
                "executor": job.executor,
                "feedback": list(job.feedback),
                "shots": [s.audio for s in job.draft.shots],
                "keyframes": len(job.keyframes),
                "aspect": job.brief.aspect_ratio,
                "reuse": job.reuse_from is not None,
            }
        )
        ws = job.workspace
        (ws / "dist").mkdir(parents=True, exist_ok=True)
        (ws / "src").mkdir(parents=True, exist_ok=True)
        (ws / "src" / "Scenes.tsx").write_text("export const Scene = () => null;", encoding="utf-8")
        (ws / "design.ready.json").write_text("{}", encoding="utf-8")
        video = ws / "dist" / "preview.mp4"
        video.write_bytes(b"fake")
        acc, captions = 0.0, []
        for s in job.draft.shots:
            captions.append({"start": acc, "end": acc + s.seconds, "text": s.audio})
            acc += s.seconds
        timeline = {
            "fps": 30,
            "scenes": [{"audio": s.audio, "frames": int(s.seconds * 30)} for s in job.draft.shots],
            "captions": captions,
        }
        (ws / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        return production_service.ProductionResult(video=video, timeline=timeline)


@pytest_asyncio.fixture
async def video_env(env, monkeypatch):
    producer = FakeProducer()
    monkeypatch.setitem(production_service.PRODUCERS, "code_animation", producer)
    probes: list[production_service.Probe] = []

    async def probe(video: Path, *, detect_silence: bool):
        return probes.pop(0) if probes else production_service.Probe(duration=10.0)

    monkeypatch.setattr(production_service, "PROBE", probe)
    async with env["factory"]() as db:
        pid = await _project(db, env, mode="animation_video")
        await ps.write_draft_version(db, pid, StudioDraft(title="601", body=BODY1, shots=SHOTS), "manual")
        await ps.finalize(db, pid)
        out = await ps.create_output(db, pid, OutputCreate(kind="video"))
        await ps.patch_output(db, out["id"], __import__("app.schemas.projects", fromlist=["OutputPatch"]).OutputPatch(
            settings={"aspect_ratio": "9:16", "executor": "codex"}
        ))
    return {**env, "producer": producer, "probes": probes, "project_id": pid, "output_id": out["id"]}


@pytest.mark.asyncio
async def test_video_flow_qa_rejects_once_then_passes(video_env, monkeypatch):
    from app.services.llm import provider

    async def no_llm(*a, **kw):  # 分镜完整、有提示词、没风格：不调模型
        raise AssertionError("不应调用模型")

    monkeypatch.setattr(provider, "call_llm_json", no_llm)
    video_env["probes"].append(production_service.Probe(duration=10.0, black=[(4.5, 6.5)]))
    async with video_env["factory"]() as db:
        res = await production_service.start_render(db, video_env["output_id"])
        run_id = res["run_id"]
        assert res["output"]["status"] == "rendering"
        await engine.wait_run(run_id)
        run = await db.get(AgentRun, run_id, populate_existing=True)
        assert run.status == "done", run.status_reason
        steps = await _steps(db, run_id)
        assert [(s.node, s.round) for s in steps] == [
            ("storyboard", 1), ("art", 1), ("produce", 1), ("qa", 1), ("produce", 2), ("qa", 2),
        ]
        assert steps[2].executor == "codex"
        jobs = video_env["producer"].jobs
        assert jobs[0]["feedback"] == [] and jobs[0]["aspect"] == "9:16" and jobs[0]["keyframes"] == 2
        assert jobs[1]["feedback"][0]["check"] == "black" and jobs[1]["feedback"][0]["shot"] == 2
        assert jobs[1]["reuse"] is True  # 上一版的设计源码被复用（在其上修改）
        # 制作读的是定稿文案；StudioArtifact 挂产出物并带 settings 快照
        assert jobs[0]["shots"] == [s["audio"] for s in SHOTS]
        arts = (
            await db.execute(select(StudioArtifact).where(StudioArtifact.output_id == video_env["output_id"]).order_by(StudioArtifact.id))
        ).scalars().all()
        assert len(arts) == 2 and all(a.status == "done" for a in arts)
        assert arts[1].settings["executor"] == "codex" and arts[1].settings["attempt"] == 2
        assert arts[1].progress["qa"]["passed"] is True
        out = await ps.output_view(db, video_env["output_id"])
        assert out["status"] == "done" and out["content"]["artifact_id"] == arts[1].id
        # 溯源：成片 → 分镜 → 文稿版本 → 采集内容
        video = (await _arts(db, run_id, "video"))[-1]
        lin = await trace_service.lineage(db, video.id)

        def walk(nodes):
            for n in nodes:
                yield n
                yield from walk(n.get("sources") or [])

        found = list(walk(lin["sources"]))
        assert any(n.get("kind") == "storyboard" for n in found)
        assert any(n.get("kind") == "draft_version" for n in found)
        assert any(n["type"] == "content" and n["id"] == video_env["content_id"] for n in found)


@pytest.mark.asyncio
async def test_video_flow_stops_after_two_rejections(video_env, monkeypatch):
    for _ in range(3):
        video_env["probes"].append(production_service.Probe(duration=30.0))
    async with video_env["factory"]() as db:
        res = await production_service.start_render(db, video_env["output_id"])
        await engine.wait_run(res["run_id"])
        run = await db.get(AgentRun, res["run_id"], populate_existing=True)
        assert run.status == "failed" and "仍未通过" in run.status_reason
        assert [s.node for s in await _steps(db, run.id)].count("produce") == 3
        out = await ps.output_view(db, video_env["output_id"])
        assert out["status"] == "failed"
        # 失败后可以从「制作」换执行者重跑（分叉），上游复用
        fork = await engine.fork_run(db, run.id, "produce", {"executor": "claude_code"})
        await engine.wait_run(fork.id)
        fsteps = await _steps(db, fork.id)
        assert [s.status for s in fsteps[:2]] == ["reused", "reused"]
        assert fsteps[2].executor == "claude_code"


@pytest.mark.asyncio
async def test_start_render_guards(video_env, monkeypatch):
    async with video_env["factory"]() as db:
        pid = await _project(db, video_env, mode="animation_video")
        with pytest.raises(AppException) as e:
            await ps.create_output(db, pid, OutputCreate(kind="video"))
        assert e.value.status_code == 409

        async def problems(db, project, output):
            return ["讲解视频需要配音"]

        monkeypatch.setattr(production_service, "PREFLIGHT", problems)
        with pytest.raises(AppException) as e:
            await production_service.start_render(db, video_env["output_id"])
        assert e.value.status_code == 503 and e.value.detail["problems"] == ["讲解视频需要配音"]


def test_evaluate_rules():
    probe = production_service.Probe(duration=10.2, black=[(0.0, 0.4), (5.0, 7.0)], silence=[(1.0, 5.5)])
    timeline = {"fps": 30, "scenes": [{"audio": "每天 601 美元。", "frames": 120}, {"audio": "别的", "frames": 180}]}
    captions = [{"start": 0, "end": 4, "text": "每天 601 美元。"}, {"start": 4, "end": 10, "text": "任务长度每七个月翻倍。"}]
    r = production_service.evaluate(kind="video", shots=SHOTS, probe=probe, timeline=timeline, captions=captions)
    by = {c["key"]: c["ok"] for c in r["checks"]}
    assert by == {"duration": True, "black": False, "silence": False, "subtitles": True, "storyboard": False}
    assert not r["passed"]
    assert {(i["check"], i.get("shot")) for i in r["issues"]} == {("black", 2), ("silence", 1), ("storyboard", 2)}
    ok = production_service.evaluate(
        kind="mv", shots=SHOTS, probe=production_service.Probe(duration=None, available=False), timeline=None, captions=None
    )
    assert ok["passed"] and ok["checks"][0]["ok"] is None


# ── 外部执行者 ──


def test_convert_claude_and_codex_events():
    ev = agent_adapters.convert_claude(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "开始设计"},
                    {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "src/Scenes.tsx"}},
                    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "npx tsc --noEmit"}},
                ]
            },
        }
    )
    assert [(e["kind"], e["name"]) for e in ev] == [("message", "assistant"), ("file_change", "Write"), ("command", "Bash")]
    res = agent_adapters.convert_claude(
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "TS2304"}]}}
    )
    assert res[0]["kind"] == "error" and res[0]["id"] == "t2"
    fin = agent_adapters.convert_claude({"type": "result", "total_cost_usd": 0.12, "usage": {"input_tokens": 10}})
    assert fin[0]["kind"] == "usage" and fin[0]["detail"]["cost_usd"] == 0.12
    cx = agent_adapters.convert_codex
    assert cx({"type": "item.completed", "item": {"type": "command_execution", "command": "ls", "exit_code": 1}})[0]["kind"] == "error"
    assert cx({"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": "src/Scenes.tsx"}]}})[0]["kind"] == "file_change"
    assert cx({"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 2}})[0]["kind"] == "usage"
    assert cx({"type": "thread.started"}) == []


@pytest.mark.asyncio
async def test_run_agent_with_fake_cli(tmp_path):
    script = tmp_path / "fake_codex.py"
    script.write_text(
        "import json, pathlib\n"
        "pathlib.Path('src').mkdir(exist_ok=True)\n"
        "pathlib.Path('src/Scenes.tsx').write_text('x')\n"
        "print(json.dumps({'type': 'thread.started'}))\n"
        "print('not json')\n"
        "print(json.dumps({'type': 'item.completed', 'item': {'type': 'file_change', 'changes': [{'path': 'src/Scenes.tsx'}]}}))\n"
        "print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 3, 'output_tokens': 4}}))\n",
        encoding="utf-8",
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    seen, stages = [], []

    async def sink(ev):
        seen.append(ev["kind"])

    async def on_stage(name, percent=None):
        stages.append(name)

    out = await agent_adapters.run_agent("codex", ws, on_stage, sink, argv=[sys.executable, str(script)])
    assert out["exit_code"] == 0 and out["events"] == {"file_change": 1, "usage": 1}
    assert seen == ["file_change", "usage"] and (ws / "design.ready.json").is_file()
    assert stages and stages[0] == "Codex 设计动画"
    assert (ws / "codex.events.jsonl").read_text(encoding="utf-8").count("\n") == 4
    bad = tmp_path / "bad.py"
    bad.write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    ws2 = tmp_path / "ws2"
    ws2.mkdir()
    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await agent_adapters.run_agent("codex", ws2, on_stage, None, argv=[sys.executable, str(bad)])


# ── 溯源入口（第 ⑤ 步）──


@pytest.mark.asyncio
async def test_anchored_lineage_paragraph_and_shot(video_env, monkeypatch):
    async with video_env["factory"]() as db:
        res = await production_service.start_render(db, video_env["output_id"])
        await engine.wait_run(res["run_id"])
        # 分镜第 2 镜 → 文稿段落 2 → 主来源
        art, anc = await project_lineage.resolve(db, target="shot", output_id=video_env["output_id"], shot=2)
        assert art.kind == "storyboard" and anc == "shot_2"
        lin = await trace_service.lineage(db, art.id, anchor=anc)
        p2 = ps.paragraphs_with_ids(BODY1)[1]["id"]
        version_nodes = [s for s in lin["sources"] if s.get("kind") == "draft_version"]
        assert {s["target_anchor"] for s in version_nodes if s["target_anchor"]} == {p2}
        assert any(n["type"] == "content" and n.get("title") for v in version_nodes for n in v.get("sources") or [])
        # 成片入口按 StudioArtifact 找到成片产物
        sa = (await ps.output_view(db, video_env["output_id"]))["content"]["artifact_id"]
        vid, _ = await project_lineage.resolve(db, target="video", output_id=video_env["output_id"], studio_artifact_id=sa)
        assert vid.kind == "video" and vid.content["studio_artifact_id"] == sa


@pytest.mark.asyncio
async def test_paragraph_markers_and_platform_lineage(env):
    async with env["factory"]() as db:
        pid = await _project(db, env)
        body = "引言。\n\n数据来自 METR [1]。\n\n结尾 [7]。"
        await ps.write_draft_version(db, pid, StudioDraft(title="t", body=body), "manual")
        await ps.finalize(db, pid)
        paras = ps.paragraphs_with_ids(body)
        art, anc = await project_lineage.resolve(db, target="paragraph", project_id=pid, anchor=paras[1]["id"])
        lin = await trace_service.lineage(db, art.id, anchor=anc)
        assert [(s["type"], s["id"]) for s in lin["sources"]] == [("content", env["content_id"])]
        assert lin["sources"][0]["title"] == "METR：任务长度翻倍"
        lin0 = await trace_service.lineage(db, art.id, anchor=paras[0]["id"])
        assert lin0["sources"] == []  # 第一段没有引用
        # 平台稿 ← 文稿版本
        out = await ps.create_output(db, pid, OutputCreate(kind="xhs"))
        plat, _ = await project_lineage.resolve(db, target="platform", output_id=out["id"])
        assert plat.kind == "platform_xhs"
        up = await trace_service.lineage(db, plat.id)
        assert up["sources"][0]["kind"] == "draft_version" and up["sources"][0]["id"] == art.id
