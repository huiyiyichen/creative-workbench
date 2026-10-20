"""流程引擎：把 YAML 流程模板编译成 LangGraph 图并管理运行（改造方案 2.2）。

LangGraph 负责：并行分支（Send）、状态持久化（PostgreSQL checkpointer，同一个库）、
人工关卡的中断与恢复（interrupt / Command(resume)）、失败后从上次完成的步骤继续。
自己做：模型调用（现有模型层）、产物与溯源（自己的表）、节点图（导出模板结构）、SSE 事件。

* 预算：每个步骤开始前检查花费 / 步数 / 时间，超限暂停（paused），由你追加预算后继续或停止。
* 停止：取消运行任务，正在执行的步骤标记为 stopped。
* 从这里重跑：新建分叉运行（parent_run_id），上游步骤直接复用原运行的产物（reused），
  从指定节点起按新设置（提示词补充、模型组）重新执行；原运行不变。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun, AgentStep, Artifact
from app.services import run_events, trace_service
from app.services.flows.roles import ROLE_IMPLS, RoleContext
from app.services.flows.spec import FlowSpec, FlowSpecError, NodeSpec, load_spec

logger = logging.getLogger(__name__)

# 测试可替换为绑定测试库的会话工厂
SESSION_FACTORY = None
_checkpointer: Any = None
_checkpointer_lock = asyncio.Lock()
_graphs: dict[tuple[str, int, int], Any] = {}
_tasks: dict[int, asyncio.Task] = {}

ACTIVE = {"queued", "running"}
FINISHED = {"done", "failed", "stopped"}


class FlowError(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class RunStopped(Exception):
    pass


def _session() -> AsyncSession:
    if SESSION_FACTORY is not None:
        return SESSION_FACTORY()
    from app.core.database import async_session

    return async_session()


def _aware(ts: datetime | None) -> datetime | None:
    if ts is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


# ── 状态 ──


def merge_outputs(a: dict | None, b: dict | None) -> dict:
    out = {k: list(v) for k, v in (a or {}).items()}
    for k, v in (b or {}).items():
        out[k] = out.get(k, []) + [i for i in v if i not in out.get(k, [])]
    return out


def merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class FlowState(TypedDict, total=False):
    run_id: int
    inputs: dict
    outputs: Annotated[dict, merge_outputs]
    decisions: Annotated[dict, merge_dict]
    rounds: Annotated[dict, merge_dict]  # 节点 → 已执行轮次（退回循环用）
    verdicts: Annotated[dict, merge_dict]  # 节点 → 最近一次产物的 passed
    branch: str | None


# ── checkpointer ──


async def get_checkpointer() -> Any:
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    async with _checkpointer_lock:
        if _checkpointer is not None:
            return _checkpointer
        from app.core.config import settings

        url = str(getattr(settings, "DATABASE_URL", "") or "")
        mode = os.environ.get("FLOW_CHECKPOINTER", "auto")
        if mode != "memory" and url.startswith("postgresql"):
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool

            conninfo = url.replace("postgresql+asyncpg://", "postgresql://").replace(
                "postgresql+psycopg://", "postgresql://"
            )
            pool = AsyncConnectionPool(
                conninfo,
                max_size=5,
                open=False,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            )
            await pool.open()
            saver = AsyncPostgresSaver(pool)
            # 首次建表含 CREATE INDEX CONCURRENTLY，会等其他事务结束；启动时在 DuckDB ATTACH 之前调用
            await asyncio.wait_for(saver.setup(), 60)
            _checkpointer = saver
        else:
            from langgraph.checkpoint.memory import InMemorySaver

            _checkpointer = InMemorySaver()
        return _checkpointer


def set_checkpointer(saver: Any) -> None:
    """测试用：换成内存 checkpointer。"""
    global _checkpointer
    _checkpointer = saver
    _graphs.clear()


# ── 编译 ──


def _input_ids(spec: FlowSpec, node: NodeSpec, state: FlowState) -> list[int]:
    """上游节点的全部产物 + reads 节点的最新一个产物（退回时的反馈、成稿修改时的原稿）。"""
    outs = state.get("outputs") or {}
    ids: list[int] = []

    def upstream(nid: str) -> list[int]:
        n = spec.node(nid)
        if n.type == "gate":  # 关卡不产出产物：把它上游的产物传下去
            return [i for g in n.after for i in upstream(g)]
        return list(outs.get(nid, []))

    for a in node.after:
        ids.extend(i for i in upstream(a) if i not in ids)
    for a in node.reads:
        latest = (outs.get(a) or [])[-1:]
        ids.extend(i for i in latest if i not in ids)
    return ids


async def _artifact_views(db: AsyncSession, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    from app.models.agent_run import ArtifactLink

    rows = {a.id: a for a in (await db.execute(select(Artifact).where(Artifact.id.in_(ids)))).scalars()}
    links: dict[int, list[ArtifactLink]] = {}
    for ln in (await db.execute(select(ArtifactLink).where(ArtifactLink.artifact_id.in_(ids)))).scalars():
        links.setdefault(ln.artifact_id, []).append(ln)
    return [trace_service.artifact_view(rows[i], links.get(i)) for i in ids if i in rows]


async def _check_budget(db: AsyncSession, run: AgentRun) -> None:
    budget = run.budget or {}
    await trace_service.refresh_run_usage(db, run.id)
    await db.refresh(run)
    cost_cap = budget.get("cost")
    if cost_cap is not None and run.cost >= float(cost_cap):
        raise BudgetExceeded(f"花费 ¥{run.cost:.2f} 已到上限 ¥{float(cost_cap):.2f}")
    steps_cap = budget.get("steps")
    if steps_cap is not None:
        n = (
            await db.execute(
                select(func.count(AgentStep.id)).where(
                    AgentStep.run_id == run.id, AgentStep.status.not_in(["reused", "waiting"])
                )
            )
        ).scalar() or 0
        if n >= int(steps_cap):
            raise BudgetExceeded(f"已执行 {n} 步，到达上限 {int(steps_cap)} 步")
    secs_cap = budget.get("seconds")
    if secs_cap is not None and run.started_at:
        waited = (
            await db.execute(
                select(func.coalesce(func.sum(AgentStep.duration_ms), 0)).where(
                    AgentStep.run_id == run.id, AgentStep.executor == "human"
                )
            )
        ).scalar() or 0
        active = (datetime.now(UTC) - _aware(run.started_at)).total_seconds() - waited / 1000
        if active >= float(secs_cap):
            raise BudgetExceeded(f"已运行 {int(active)} 秒，到达上限 {int(secs_cap)} 秒")


def _make_role_node(spec: FlowSpec, node: NodeSpec):
    async def run_node(state: FlowState) -> dict[str, Any]:
        run_id = state["run_id"]
        inputs = state.get("inputs") or {}
        branch = state.get("branch") if node.parallel else None
        input_ids = _input_ids(spec, node, state)
        rnd = int((state.get("rounds") or {}).get(node.id) or 0) + 1
        async with _session() as db:
            run = await db.get(AgentRun, run_id, populate_existing=True)
            if run is None or run.status == "stopped":
                raise RunStopped("运行已停止")
            reuse = ((inputs.get("_reuse") or {}).get(node.id) or {}).get(branch or "")
            if reuse is not None:
                step = await trace_service.start_step(
                    db,
                    run_id,
                    node=node.id,
                    role=node.role or "",
                    label=node.label,
                    executor=node.executor,
                    branch=branch,
                    input_artifact_ids=input_ids,
                    meta={"reused_from_run": run.parent_run_id},
                    status="reused",
                )
                await trace_service.finish_step(db, step, status="reused", output_artifact_ids=list(reuse))
                return {"outputs": {node.id: list(reuse)}, "rounds": {node.id: rnd}}
            await _check_budget(db, run)
            override = (inputs.get("_overrides") or {}).get(node.id) or {}
            step = await trace_service.start_step(
                db,
                run_id,
                node=node.id,
                role=node.role or "",
                label=node.label,
                executor=_executor(node, inputs, override),
                branch=branch,
                round=rnd,
                input_artifact_ids=input_ids,
                meta={
                    "params": node.params,
                    "routing_group": override.get("routing_group") or node.routing_group,
                    **({"override": override} if override else {}),
                },
            )
            try:
                ctx = RoleContext(
                    db=db,
                    run_id=run_id,
                    step_id=step.id,
                    node=node,
                    inputs=inputs,
                    branch=branch,
                    input_artifacts=await _artifact_views(db, input_ids),
                    override=override,
                    decisions=dict(state.get("decisions") or {}),
                    round=rnd,
                    executor=_executor(node, inputs, override),
                )
                outs = await ROLE_IMPLS[node.role or ""](ctx)
                ids = []
                for o in outs:
                    art = await trace_service.add_artifact(
                        db,
                        kind=o.kind,
                        title=o.title,
                        content=o.content,
                        run_id=run_id,
                        step_id=step.id,
                        project_id=run.project_id,
                        links=o.links,
                    )
                    ids.append(art.id)
                summary = None
                update: dict[str, Any] = {"outputs": {node.id: ids}, "rounds": {node.id: rnd}}
                if outs:
                    c = outs[0].content
                    summary = c.get("summary") or (f"{len(c.get('cards') or [])} 个方向" if "cards" in c else None)
                    if "passed" in c:
                        update["verdicts"] = {node.id: bool(c["passed"])}
                elif ctx.summary:
                    summary = ctx.summary
                await trace_service.finish_step(
                    db, step, output_artifact_ids=ids, meta={"summary": summary} if summary else None
                )
                return update
            except asyncio.CancelledError:
                await db.rollback()
                await trace_service.finish_step(db, step, status="stopped", error="运行被停止")
                raise
            except Exception as exc:
                await db.rollback()
                await trace_service.finish_step(db, step, status="failed", error=str(exc) or exc.__class__.__name__)
                raise

    run_node.__name__ = f"node_{node.id}"
    return run_node


ACCEPT_OPTIONS = [{"id": "accept", "title": "接受"}, {"id": "reject", "title": "不接受"}]


def gate_options(arts: list[dict[str, Any]], kind: str | None = None) -> list[dict[str, Any]]:
    if kind == "accept":
        return [dict(o) for o in ACCEPT_OPTIONS]
    for a in reversed(arts):
        if a["kind"] == "direction_cards":
            return [{**c, "artifact_id": a["id"]} for c in (a.get("content") or {}).get("cards") or []]
    return []


def _make_gate_node(spec: FlowSpec, node: NodeSpec):
    from langgraph.types import interrupt

    async def gate_node(state: FlowState) -> dict[str, Any]:
        run_id = state["run_id"]
        inputs = state.get("inputs") or {}
        enabled = (inputs.get("_gates") or {}).get(node.id, node.gate.get("enabled", True))
        input_ids = _input_ids(spec, node, state)
        async with _session() as db:
            options = gate_options(await _artifact_views(db, input_ids), node.gate.get("kind"))
            if not enabled:
                step = await trace_service.start_step(
                    db,
                    run_id,
                    node=node.id,
                    role="gate",
                    label=node.label,
                    executor="human",
                    input_artifact_ids=input_ids,
                    meta={"auto": True},
                )
                auto = "关卡已关闭，自动接受" if node.gate.get("kind") == "accept" else "关卡已关闭，保留全部方向"
                await trace_service.finish_step(db, step, meta={"summary": auto})
                return {"decisions": {node.id: {"auto": True}}}
            # interrupt 恢复时节点会从头再跑一遍：复用已在等待的步骤
            step = (
                await db.execute(
                    select(AgentStep)
                    .where(AgentStep.run_id == run_id, AgentStep.node == node.id, AgentStep.status == "waiting")
                    .order_by(AgentStep.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if step is None:
                step = await trace_service.start_step(
                    db,
                    run_id,
                    node=node.id,
                    role="gate",
                    label=node.label,
                    executor="human",
                    input_artifact_ids=input_ids,
                    meta={"gate": node.gate.get("kind"), "options": options},
                    status="waiting",
                )
                run = await db.get(AgentRun, run_id, populate_existing=True)
                run.status = "waiting"
                run.status_reason = f"等待你处理：{node.label}"
                await db.commit()
                await run_events.publish(run_id, {"type": "run", "run": trace_service.run_view(run)})
                await _notify_gate(run, node)
            step_id = step.id
        choice = interrupt({"gate": node.id, "step_id": step_id, "options": options})
        async with _session() as db:
            step = await db.get(AgentStep, step_id, populate_existing=True)
            await trace_service.record_decision(
                db,
                run_id=run_id,
                step_id=step_id,
                gate=node.id,
                options=options,
                choice=choice,
                note=(choice or {}).get("note"),
            )
            label = (choice or {}).get("title") or (choice or {}).get("custom") or "已选择"
            await trace_service.finish_step(db, step, meta={"summary": f"选择：{label}", "choice": choice})
            run = await db.get(AgentRun, run_id, populate_existing=True)
            run.status = "running"
            run.status_reason = None
            await db.commit()
            await run_events.publish(run_id, {"type": "run", "run": trace_service.run_view(run)})
        return {"decisions": {node.id: choice}}

    gate_node.__name__ = f"gate_{node.id}"
    return gate_node


async def _notify_gate(run: AgentRun, node: NodeSpec) -> None:
    """流程停在关卡时通知你（失败不影响流程）。"""
    if SESSION_FACTORY is not None:  # 测试环境不发通知
        return
    try:
        from app.services.notification_service import push_notification

        await push_notification("info", "flow", f"等待处理：{node.label}", f"{run.title}（/runs/{run.id}）")
    except Exception:  # noqa: BLE001
        logger.debug("gate notification skipped", exc_info=True)


def compile_graph(spec: FlowSpec, checkpointer: Any) -> Any:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Send

    g = StateGraph(FlowState)
    for n in spec.nodes:
        g.add_node(n.id, _make_gate_node(spec, n) if n.type == "gate" else _make_role_node(spec, n))
    for n in spec.nodes:
        if n.parallel:
            if len(n.after) > 1:
                raise FlowSpecError(f"并行节点 {n.id} 只能有一个上游")

            def route(state: FlowState, n: NodeSpec = n) -> list[Any]:
                items = [str(x) for x in (state.get("inputs") or {}).get(n.parallel) or []] or [""]
                return [Send(n.id, {**state, "branch": b or None}) for b in items]

            g.add_conditional_edges(n.after[0] if n.after else START, route, [n.id])
        elif not n.after:
            g.add_edge(START, n.id)
        elif any(spec.node(a).loop_to for a in n.after):
            if len(n.after) > 1:
                raise FlowSpecError(f"节点 {n.id} 接在退回节点后面时只能有一个上游")
            # 边由退回节点的条件路由给出
        elif len(n.after) == 1:
            g.add_edge(n.after[0], n.id)
        else:
            g.add_edge(n.after, n.id)
    upstream = {a for n in spec.nodes for a in n.after}
    for n in spec.nodes:
        if n.loop_to:
            downstream = [m.id for m in spec.nodes if n.id in m.after]
            if any(m.parallel for m in spec.nodes if m.id in downstream):
                raise FlowSpecError(f"退回节点 {n.id} 的下游不能是并行节点")

            def loop_route(state: FlowState, n: NodeSpec = n, downstream: list[str] = downstream) -> Any:
                passed = (state.get("verdicts") or {}).get(n.id, True)
                done = int((state.get("rounds") or {}).get(n.loop_to) or 0)
                if not passed and done <= n.max_loops:
                    return n.loop_to
                return downstream or END

            g.add_conditional_edges(n.id, loop_route, [n.loop_to, *(downstream or [END])])
            continue
        if n.id not in upstream:
            g.add_edge(n.id, END)
    return g.compile(checkpointer=checkpointer)


def _executor(node: NodeSpec, inputs: dict[str, Any], override: dict[str, Any]) -> str:
    """执行者：重跑设置 > 运行输入里按节点指定（例如产出物的执行者设置）> 模板。"""
    return str(override.get("executor") or (inputs.get("_executors") or {}).get(node.id) or node.executor)


async def get_graph(spec: FlowSpec) -> Any:
    saver = await get_checkpointer()
    key = (spec.key, spec.version, id(saver))
    if key not in _graphs:
        _graphs[key] = compile_graph(spec, saver)
    return _graphs[key]


# ── 运行 ──


def _config(run: AgentRun) -> dict[str, Any]:
    return {"configurable": {"thread_id": run.thread_id}, "recursion_limit": 100}


async def _set_status(run_id: int, status: str, reason: str | None = None, **fields: Any) -> None:
    async with _session() as db:
        run = await db.get(AgentRun, run_id, populate_existing=True)
        if run is None:
            return
        run.status = status
        run.status_reason = reason
        for k, v in fields.items():
            setattr(run, k, v)
        if status in FINISHED or status == "paused":
            # 还挂着 running 的步骤（被取消 / 崩溃）收尾
            for s in (
                await db.execute(select(AgentStep).where(AgentStep.run_id == run_id, AgentStep.status == "running"))
            ).scalars():
                s.status = "stopped" if status == "stopped" else "failed"
                s.finished_at = datetime.now(UTC)
                s.error = s.error or reason
        await db.commit()
        await trace_service.refresh_run_usage(db, run_id)
        await db.refresh(run)
        await run_events.publish(run_id, {"type": "run", "run": trace_service.run_view(run)})


async def _final_outputs(run_id: int, state: dict[str, Any]) -> dict[str, Any]:
    outs = state.get("outputs") or {}
    decisions = state.get("decisions") or {}
    return {"artifacts": outs, "decisions": decisions}


async def _drive(run_id: int, command: Any) -> None:
    async with _session() as db:
        run = await db.get(AgentRun, run_id, populate_existing=True)
        if run is None:
            return
        spec = load_spec(run.flow_key)
        config = _config(run)
        if run.started_at is None:
            run.started_at = datetime.now(UTC)
        run.status = "running"
        run.status_reason = None
        await db.commit()
        await run_events.publish(run_id, {"type": "run", "run": trace_service.run_view(run)})
    graph = await get_graph(spec)
    try:
        async for _chunk in graph.astream(command, config, stream_mode="updates"):
            pass
        snap = await graph.aget_state(config)
        if snap.next:  # 停在关卡
            async with _session() as db:
                run = await db.get(AgentRun, run_id, populate_existing=True)
                if run and run.status != "waiting":
                    run.status = "waiting"
                    await db.commit()
            return
        failed_loops = [
            n.label for n in spec.nodes if n.loop_to and (snap.values.get("verdicts") or {}).get(n.id) is False
        ]
        if failed_loops:
            await _set_status(
                run_id,
                "failed",
                f"{'、'.join(failed_loops)}退回 {max(n.max_loops for n in spec.nodes if n.loop_to)} 次后仍未通过，已停下。"
                "可以在节点图里查看问题，或从「制作」重跑。",
                finished_at=datetime.now(UTC),
                outputs=await _final_outputs(run_id, snap.values),
            )
        else:
            await _set_status(
                run_id, "done", None, finished_at=datetime.now(UTC), outputs=await _final_outputs(run_id, snap.values)
            )
    except BudgetExceeded as exc:
        await _set_status(run_id, "paused", f"超出预算：{exc}。可以追加预算后继续，或停止。")
    except (asyncio.CancelledError, RunStopped):
        await _set_status(run_id, "stopped", "已停止", finished_at=datetime.now(UTC))
    except Exception as exc:  # noqa: BLE001
        logger.warning("flow run %s failed", run_id, exc_info=True)
        await _set_status(run_id, "failed", str(exc) or exc.__class__.__name__, finished_at=datetime.now(UTC))
    finally:
        _tasks.pop(run_id, None)
        await _run_finish_hook(run_id)


# 流程结束（完成 / 失败 / 停止 / 暂停）时的业务回调：按流程 key 懒加载，避免引擎依赖业务服务
FINISH_HOOKS: dict[str, str] = {
    "video_production": "app.services.production_service:on_run_finished",
    "draft_writing": "app.services.draft_flow:on_run_finished",
    "platform_rewrite": "app.services.platform_flow:on_run_finished",
}


async def _run_finish_hook(run_id: int) -> None:
    try:
        async with _session() as db:
            run = await db.get(AgentRun, run_id, populate_existing=True)
            if run is None or run.status in ACTIVE or run.status == "waiting":
                return
            target = FINISH_HOOKS.get(run.flow_key)
            if not target:
                return
            import importlib

            mod, fn = target.split(":")
            await getattr(importlib.import_module(mod), fn)(db, run)
    except Exception:  # noqa: BLE001
        logger.warning("finish hook failed for run %s", run_id, exc_info=True)


def _launch(run_id: int, command: Any) -> asyncio.Task:
    old = _tasks.get(run_id)
    if old is not None and not old.done():
        raise FlowError("这个运行正在执行")
    task = asyncio.create_task(_drive(run_id, command), name=f"flow-run-{run_id}")
    _tasks[run_id] = task
    return task


async def wait_run(run_id: int, timeout: float = 60) -> None:
    task = _tasks.get(run_id)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), timeout)


def _validate_inputs(spec: FlowSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, meta in spec.inputs.items():
        val = inputs.get(name, meta.get("default"))
        if meta.get("type") == "list":
            val = list(val or [])
            opts = meta.get("options")
            if opts:
                val = [v for v in val if v in opts]
        elif meta.get("type") == "dict":
            val = dict(val or {})
        elif val is not None:
            val = str(val).strip()
        if meta.get("required") and not val:
            raise FlowError(f"缺少「{meta.get('label') or name}」")
        out[name] = val
    return out


async def start_run(
    db: AsyncSession,
    flow_key: str,
    inputs: dict[str, Any],
    *,
    title: str | None = None,
    gates: dict[str, bool] | None = None,
    budget: dict[str, Any] | None = None,
    trigger: str = "manual",
    project_id: int | None = None,
    launch: bool = True,
) -> AgentRun:
    try:
        spec = load_spec(flow_key)
    except FlowSpecError as exc:
        raise FlowError(str(exc)) from exc
    clean = _validate_inputs(spec, inputs)
    gates = {k: bool(v) for k, v in (gates or {}).items() if any(n.id == k and n.type == "gate" for n in spec.nodes)}
    for k in list(gates):
        if not spec.node(k).gate.get("can_disable") and not gates[k]:
            gates.pop(k)  # 不可关闭的关卡（例如定稿）忽略
    if gates:
        clean["_gates"] = gates
    topic = clean.get("topic") or ""
    run = AgentRun(
        flow_key=spec.key,
        flow_version=spec.version,
        title=title or (f"{spec.name} · {topic}" if topic else spec.name)[:300],
        project_id=project_id,
        trigger=trigger,
        status="queued",
        inputs=clean,
        budget={**spec.budget, **(budget or {})},
        graph=spec.graph_view(gates),
        thread_id=uuid.uuid4().hex,
    )
    db.add(run)
    await db.commit()
    await run_events.publish(run.id, {"type": "run", "run": trace_service.run_view(run)})
    if launch:
        _launch(run.id, {"run_id": run.id, "inputs": clean, "outputs": {}, "decisions": {}})
    return run


async def _pending_gate(db: AsyncSession, run_id: int) -> AgentStep | None:
    return (
        await db.execute(
            select(AgentStep)
            .where(AgentStep.run_id == run_id, AgentStep.status == "waiting")
            .order_by(AgentStep.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def resume_gate(db: AsyncSession, run_id: int, choice: dict[str, Any]) -> AgentRun:
    """人工关卡：选一个方向（card_id），或写自己的方向（custom）。"""
    from langgraph.types import Command

    run = await db.get(AgentRun, run_id, populate_existing=True)
    if run is None:
        raise FlowError("运行不存在")
    if run.status != "waiting":
        raise FlowError("这个运行没有在等待关卡")
    step = await _pending_gate(db, run_id)
    if step is None:
        raise FlowError("没有待处理的关卡")
    options = (step.meta or {}).get("options") or []
    note = (choice.get("note") or "").strip() or None
    if choice.get("card_id"):
        picked = next((o for o in options if o.get("id") == choice["card_id"]), None)
        if picked is None:
            raise FlowError("没有这个方向")
        value = {"card_id": picked["id"], "title": picked.get("title"), "artifact_id": picked.get("artifact_id")}
    elif (choice.get("custom") or "").strip():
        value = {"custom": choice["custom"].strip()[:500]}
    else:
        raise FlowError("请选择一个方向或写下你的方向")
    if note:
        value["note"] = note[:500]
    _launch(run_id, Command(resume=value))
    return run


async def continue_run(db: AsyncSession, run_id: int, add_budget: dict[str, Any] | None = None) -> AgentRun:
    """超预算暂停 / 失败 / 服务重启中断后，从上次完成的步骤继续（可追加预算）。"""
    run = await db.get(AgentRun, run_id, populate_existing=True)
    if run is None:
        raise FlowError("运行不存在")
    if run.status not in ("paused", "failed"):
        raise FlowError("只有暂停或失败的运行可以继续")
    if add_budget:
        budget = dict(run.budget or {})
        for k in ("cost", "seconds", "steps"):
            if add_budget.get(k):
                budget[k] = float(budget.get(k) or 0) + float(add_budget[k])
        if "steps" in budget:
            budget["steps"] = int(budget["steps"])
        run.budget = budget
    run.finished_at = None
    run.status = "queued"
    run.status_reason = None
    await db.commit()
    _launch(run_id, None)
    return run


async def stop_run(db: AsyncSession, run_id: int) -> AgentRun:
    run = await db.get(AgentRun, run_id, populate_existing=True)
    if run is None:
        raise FlowError("运行不存在")
    if run.status in FINISHED:
        return run
    task = _tasks.get(run_id)
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 10)
    else:
        await _set_status(run_id, "stopped", "已停止", finished_at=datetime.now(UTC))
    await db.refresh(run)
    return run


async def fork_run(
    db: AsyncSession, run_id: int, node_id: str, override: dict[str, Any] | None = None, *, launch: bool = True
) -> AgentRun:
    """从某个节点重跑：上游复用原产物，从该节点起按新设置执行；原运行保留。"""
    parent = await db.get(AgentRun, run_id, populate_existing=True)
    if parent is None:
        raise FlowError("运行不存在")
    spec = load_spec(parent.flow_key)
    try:
        node = spec.node(node_id)
    except FlowSpecError as exc:
        raise FlowError(str(exc)) from exc
    if node.type == "gate":
        raise FlowError("关卡不能重跑，请从它前面的节点重跑")
    upstream = spec.ancestors(node_id)
    reuse: dict[str, dict[str, list[int]]] = {}
    steps = (
        (
            await db.execute(
                select(AgentStep)
                .where(AgentStep.run_id == run_id, AgentStep.status.in_(["done", "reused"]))
                .order_by(AgentStep.id)
            )
        )
        .scalars()
        .all()
    )
    for s in steps:
        if s.node in upstream and spec.node(s.node).type != "gate":
            reuse.setdefault(s.node, {})[s.branch or ""] = list(s.output_artifact_ids or [])
    missing = [n for n in upstream if spec.node(n).type != "gate" and n not in reuse]
    if missing:
        raise FlowError(f"上游节点 {', '.join(sorted(missing))} 还没有完成，不能从这里重跑")
    inputs = {k: v for k, v in (parent.inputs or {}).items() if k not in ("_reuse", "_overrides")}
    inputs["_reuse"] = reuse
    clean_override = {
        k: v
        for k, v in (override or {}).items()
        if k in ("prompt_extra", "routing_group", "executor") and str(v or "").strip()
    }
    if clean_override:
        inputs["_overrides"] = {node_id: clean_override}
    run = AgentRun(
        flow_key=parent.flow_key,
        flow_version=spec.version,
        title=f"{parent.title} · 从「{node.label}」重跑"[:300],
        project_id=parent.project_id,
        trigger="fork",
        status="queued",
        inputs=inputs,
        budget=dict(parent.budget or spec.budget),
        graph=parent.graph or spec.graph_view(),
        thread_id=uuid.uuid4().hex,
        parent_run_id=parent.id,
        fork_node=node_id,
    )
    db.add(run)
    await db.commit()
    if launch:
        _launch(run.id, {"run_id": run.id, "inputs": inputs, "outputs": {}, "decisions": {}})
    return run


async def recover_on_startup() -> int:
    """服务重启：仍标记为运行中的流程改为暂停，可点「继续」从上次完成的步骤接着跑。"""
    async with _session() as db:
        rows = (await db.execute(select(AgentRun).where(AgentRun.status.in_(list(ACTIVE))))).scalars().all()
        for run in rows:
            if run.id in _tasks:
                continue
            run.status = "paused"
            run.status_reason = "服务重启，运行中断。可以点「继续」从上次完成的步骤接着跑。"
            for s in (
                await db.execute(select(AgentStep).where(AgentStep.run_id == run.id, AgentStep.status == "running"))
            ).scalars():
                s.status = "failed"
                s.error = "服务重启中断"
        await db.commit()
        return len(rows)


def flows_catalog() -> list[dict[str, Any]]:
    from app.services.flows.spec import list_specs

    return [
        {
            "key": s.key,
            "name": s.name,
            "version": s.version,
            "description": s.description,
            "inputs": s.inputs,
            "budget": s.budget,
            "graph": s.graph_view(),
        }
        for s in list_specs()
    ]
