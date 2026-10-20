"""运行记录与溯源（改造方案 2.3）：步骤、调用树、产物与来源关系、人工决定、运行视图查询。

* 模型调用由模型层写 ``llm_call_logs``（``llm_call_context`` 带 run_id / step_id），这里在查询时并入调用树。
* 工具调用与外部 agent 事件写 ``trace_spans``；完整参数与结果压缩脱敏后存 ``data/traces/``，库里只存引用和摘要。
* 产物写 ``artifacts``，来源写 ``artifact_links``（可细到简报条目锚点）。
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentDecision, AgentRun, AgentStep, Artifact, ArtifactLink, TraceSpan
from app.models.llm_model import LlmCallLog
from app.services import run_events
from app.services.trace_payloads import load_payload, save_payload, summarize


def _aware(ts: datetime | None) -> datetime | None:
    if ts is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


def _ms(start: datetime | None, end: datetime | None) -> int | None:
    start, end = _aware(start), _aware(end)
    if not start or not end:
        return None
    return int((end - start).total_seconds() * 1000)


# ── 写入 ──


async def start_step(
    db: AsyncSession,
    run_id: int,
    *,
    node: str,
    role: str,
    label: str,
    executor: str = "internal",
    branch: str | None = None,
    round: int = 1,
    input_artifact_ids: list[int] | None = None,
    meta: dict[str, Any] | None = None,
    status: str = "running",
) -> AgentStep:
    attempt = (
        await db.execute(
            select(func.count(AgentStep.id)).where(
                AgentStep.run_id == run_id,
                AgentStep.node == node,
                AgentStep.round == round,
                AgentStep.branch.is_(None) if branch is None else AgentStep.branch == branch,
            )
        )
    ).scalar() or 0
    step = AgentStep(
        run_id=run_id,
        node=node,
        role=role,
        label=label,
        executor=executor,
        branch=branch,
        round=round,
        attempt=attempt + 1,
        status=status,
        input_artifact_ids=input_artifact_ids or [],
        meta=meta or {},
        started_at=datetime.now(UTC),
    )
    db.add(step)
    await db.commit()
    await run_events.publish(run_id, {"type": "step", "step": step_view(step)})
    return step


async def _step_usage(db: AsyncSession, step_id: int) -> tuple[int, int, float, str | None]:
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(LlmCallLog.input_tokens), 0),
                func.coalesce(func.sum(LlmCallLog.output_tokens), 0),
                func.coalesce(func.sum(LlmCallLog.total_cost), 0.0),
                func.max(LlmCallLog.actual_model),
            ).where(LlmCallLog.step_id == str(step_id))
        )
    ).one()
    return int(row[0]), int(row[1]), float(row[2]), row[3]


async def finish_step(
    db: AsyncSession,
    step: AgentStep,
    *,
    status: str = "done",
    output_artifact_ids: list[int] | None = None,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AgentStep:
    await db.refresh(step)  # 回滚后对象已过期，先重新加载
    now = datetime.now(UTC)
    tin, tout, cost, model = await _step_usage(db, step.id)
    step.status = status
    step.finished_at = now
    step.duration_ms = _ms(step.started_at, now)
    step.input_tokens, step.output_tokens, step.cost = tin, tout, round(cost, 6)
    step.model = model or step.model
    if output_artifact_ids is not None:
        step.output_artifact_ids = output_artifact_ids
    if error:
        step.error = error[:4000]
    if meta:
        step.meta = {**(step.meta or {}), **meta}
    await db.commit()
    await refresh_run_usage(db, step.run_id)
    await run_events.publish(step.run_id, {"type": "step", "step": step_view(step)})
    return step


async def refresh_run_usage(db: AsyncSession, run_id: int) -> AgentRun | None:
    run = await db.get(AgentRun, run_id)
    if run is None:
        return None
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(LlmCallLog.input_tokens), 0),
                func.coalesce(func.sum(LlmCallLog.output_tokens), 0),
                func.coalesce(func.sum(LlmCallLog.total_cost), 0.0),
            ).where(LlmCallLog.run_id == str(run_id))
        )
    ).one()
    run.input_tokens, run.output_tokens, run.cost = int(row[0]), int(row[1]), round(float(row[2]), 6)
    await db.commit()
    return run


@asynccontextmanager
async def span(
    db: AsyncSession,
    *,
    kind: str,
    name: str,
    run_id: int | None = None,
    step_id: int | None = None,
    parent_id: int | None = None,
    attributes: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    via: str = "flow",
    token_id: int | None = None,
):
    """记录一次工具调用 / 外部 agent 事件。用法：``async with span(...) as rec: rec["result"] = ...``。"""
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    rec: dict[str, Any] = {"result": None, "summary": None}
    error: str | None = None
    try:
        yield rec
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        raise
    finally:
        full = {**(payload or {}), "result": rec.get("result")}
        if error:
            full["error"] = error
        ref = save_payload(f"span-{uuid.uuid4().hex}", full)
        sp = TraceSpan(
            run_id=run_id,
            step_id=step_id,
            parent_id=parent_id,
            kind=kind,
            name=name,
            status="error" if error else "ok",
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            attributes=attributes or {},
            summary=rec.get("summary") or summarize(str(rec.get("result"))[:2000] if rec.get("result") else None),
            payload_ref=ref,
            error=error,
            via=via,
            token_id=token_id,
        )
        db.add(sp)
        await db.commit()
        if run_id:
            await run_events.publish(run_id, {"type": "span", "span": span_view(sp)})


async def add_artifact(
    db: AsyncSession,
    *,
    kind: str,
    title: str,
    content: dict[str, Any] | None,
    run_id: int | None = None,
    step_id: int | None = None,
    project_id: int | None = None,
    links: list[dict[str, Any]] | None = None,
) -> Artifact:
    """登记产物与来源。links: [{relation, target_type, target_id?, target_url?, anchor?, target_anchor?}]"""
    version = 1
    if project_id is not None:
        version = (
            (
                await db.execute(
                    select(func.max(Artifact.version)).where(Artifact.project_id == project_id, Artifact.kind == kind)
                )
            ).scalar()
            or 0
        ) + 1
    art = Artifact(
        kind=kind,
        title=title[:300],
        content=content,
        run_id=run_id,
        step_id=step_id,
        project_id=project_id,
        version=version,
    )
    db.add(art)
    await db.flush()
    seen: set[tuple] = set()
    for ln in links or []:
        key = (
            ln.get("relation"),
            ln.get("target_type"),
            ln.get("target_id"),
            ln.get("target_url"),
            ln.get("anchor"),
        )
        if key in seen or not ln.get("target_type"):
            continue
        seen.add(key)
        db.add(
            ArtifactLink(
                artifact_id=art.id,
                relation=ln.get("relation") or "derived_from",
                target_type=ln["target_type"],
                target_id=ln.get("target_id"),
                target_url=(ln.get("target_url") or None) and str(ln["target_url"])[:1024],
                anchor=ln.get("anchor"),
                target_anchor=ln.get("target_anchor"),
            )
        )
    await db.commit()
    return art


async def record_decision(
    db: AsyncSession,
    *,
    run_id: int | None,
    step_id: int | None,
    gate: str,
    options: Any,
    choice: dict[str, Any] | None,
    note: str | None = None,
) -> AgentDecision:
    d = AgentDecision(run_id=run_id, step_id=step_id, gate=gate, options=options, choice=choice, note=note)
    db.add(d)
    await db.commit()
    return d


# ── 视图 ──


def run_view(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "flow_key": run.flow_key,
        "flow_version": run.flow_version,
        "title": run.title,
        "project_id": run.project_id,
        "trigger": run.trigger,
        "status": run.status,
        "status_reason": run.status_reason,
        "inputs": run.inputs or {},
        "budget": run.budget or {},
        "outputs": run.outputs,
        "cost": run.cost,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "parent_run_id": run.parent_run_id,
        "fork_node": run.fork_node,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": _ms(run.started_at, run.finished_at or (datetime.now(UTC) if run.started_at else None)),
    }


def step_view(s: AgentStep) -> dict[str, Any]:
    return {
        "id": s.id,
        "run_id": s.run_id,
        "node": s.node,
        "branch": s.branch,
        "role": s.role,
        "label": s.label,
        "executor": s.executor,
        "status": s.status,
        "attempt": s.attempt,
        "round": s.round,
        "input_artifact_ids": s.input_artifact_ids or [],
        "output_artifact_ids": s.output_artifact_ids or [],
        "model": s.model,
        "input_tokens": s.input_tokens,
        "output_tokens": s.output_tokens,
        "cost": s.cost,
        "started_at": s.started_at,
        "finished_at": s.finished_at,
        "duration_ms": s.duration_ms,
        "error": s.error,
        "meta": s.meta or {},
    }


def span_view(sp: TraceSpan) -> dict[str, Any]:
    return {
        "id": f"t{sp.id}",
        "kind": sp.kind,
        "name": sp.name,
        "status": sp.status,
        "step_id": sp.step_id,
        "parent_id": f"t{sp.parent_id}" if sp.parent_id else None,
        "started_at": sp.started_at,
        "ended_at": sp.ended_at,
        "duration_ms": sp.duration_ms,
        "attributes": sp.attributes or {},
        "summary": sp.summary,
        "error": sp.error,
        "has_payload": bool(sp.payload_ref),
        "via": sp.via,
        "cost": 0.0,
    }


def llm_span_view(log: LlmCallLog) -> dict[str, Any]:
    started = _aware(log.created_at)
    return {
        "id": f"m{log.id}",
        "kind": "llm",
        "name": log.scene,
        "status": "ok" if (log.status or "").upper() in ("DONE", "OK", "SUCCESS") else "error",
        "step_id": int(log.step_id) if (log.step_id or "").isdigit() else None,
        "parent_id": None,
        "started_at": started,
        "ended_at": None,
        "duration_ms": log.duration_ms,
        "attributes": {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": log.request_model,
            "gen_ai.response.model": log.actual_model,
            "gen_ai.usage.input_tokens": log.input_tokens,
            "gen_ai.usage.output_tokens": log.output_tokens,
        },
        "summary": log.response_summary or log.prompt_summary,
        "error": log.error_message,
        "has_payload": bool(log.payload_ref),
        "via": "flow",
        "cost": log.total_cost,
    }


def artifact_view(a: Artifact, links: list[ArtifactLink] | None = None) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "version": a.version,
        "title": a.title,
        "content": a.content,
        "run_id": a.run_id,
        "step_id": a.step_id,
        "project_id": a.project_id,
        "created_at": a.created_at,
        "links": [
            {
                "relation": ln.relation,
                "target_type": ln.target_type,
                "target_id": ln.target_id,
                "target_url": ln.target_url,
                "anchor": ln.anchor,
                "target_anchor": ln.target_anchor,
            }
            for ln in links or []
        ],
    }


async def run_detail(db: AsyncSession, run_id: int) -> dict[str, Any] | None:
    run = await db.get(AgentRun, run_id)
    if run is None:
        return None
    steps = (
        (await db.execute(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.id))).scalars().all()
    )
    arts = (await db.execute(select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.id))).scalars().all()
    links: dict[int, list[ArtifactLink]] = {}
    if arts:
        for ln in (
            await db.execute(select(ArtifactLink).where(ArtifactLink.artifact_id.in_([a.id for a in arts])))
        ).scalars():
            links.setdefault(ln.artifact_id, []).append(ln)
    decisions = (
        (await db.execute(select(AgentDecision).where(AgentDecision.run_id == run_id).order_by(AgentDecision.id)))
        .scalars()
        .all()
    )
    forks = (
        (await db.execute(select(AgentRun).where(AgentRun.parent_run_id == run_id).order_by(AgentRun.id)))
        .scalars()
        .all()
    )
    return {
        "run": run_view(run),
        "graph": run.graph or {},
        "steps": [step_view(s) for s in steps],
        "artifacts": [artifact_view(a, links.get(a.id)) for a in arts],
        "decisions": [
            {
                "id": d.id,
                "gate": d.gate,
                "step_id": d.step_id,
                "options": d.options,
                "choice": d.choice,
                "note": d.note,
                "decided_at": d.decided_at,
            }
            for d in decisions
        ],
        "forks": [{"id": f.id, "title": f.title, "status": f.status, "fork_node": f.fork_node} for f in forks],
    }


async def trace_tree(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    """运行 → 步骤 → 模型调用 / 工具调用 / 外部 agent 事件。"""
    steps = (
        (await db.execute(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.id))).scalars().all()
    )
    spans = (
        (await db.execute(select(TraceSpan).where(TraceSpan.run_id == run_id).order_by(TraceSpan.id))).scalars().all()
    )
    logs = (
        (await db.execute(select(LlmCallLog).where(LlmCallLog.run_id == str(run_id)).order_by(LlmCallLog.id)))
        .scalars()
        .all()
    )
    children: dict[int | None, list[dict[str, Any]]] = {}
    for sp in spans:
        children.setdefault(sp.step_id, []).append(span_view(sp))
    for lg in logs:
        v = llm_span_view(lg)
        children.setdefault(v["step_id"], []).append(v)
    out = []
    for s in steps:
        kids = sorted(children.get(s.id, []), key=lambda x: _aware(x["started_at"]) or datetime.min.replace(tzinfo=UTC))
        out.append(
            {
                **step_view(s),
                "children": kids,
                "tool_calls": sum(1 for k in kids if k["kind"] == "tool"),
                "llm_calls": sum(1 for k in kids if k["kind"] == "llm"),
            }
        )
    return out


async def step_detail(db: AsyncSession, step_id: int) -> dict[str, Any] | None:
    s = await db.get(AgentStep, step_id)
    if s is None:
        return None
    tree = {n["id"]: n for n in await trace_tree(db, s.run_id)}
    node = tree.get(s.id) or {**step_view(s), "children": []}
    ids = list({*(s.input_artifact_ids or []), *(s.output_artifact_ids or [])})
    arts = {}
    if ids:
        for a in (await db.execute(select(Artifact).where(Artifact.id.in_(ids)))).scalars():
            arts[a.id] = artifact_view(a)
    # 渲染后的完整提示词：取该步骤第一次模型调用的载荷
    prompt = None
    first_llm = next((c for c in node["children"] if c["kind"] == "llm" and c["has_payload"]), None)
    if first_llm:
        prompt = await span_payload(db, first_llm["id"])
    return {
        **node,
        "inputs": [arts[i] for i in s.input_artifact_ids or [] if i in arts],
        "outputs": [arts[i] for i in s.output_artifact_ids or [] if i in arts],
        "prompt": prompt,
    }


async def span_payload(db: AsyncSession, span_id: str) -> dict[str, Any] | None:
    """调用树载荷按需加载：t<id> 工具 / 事件，m<id> 模型调用。"""
    ref = None
    if span_id.startswith("t") and span_id[1:].isdigit():
        sp = await db.get(TraceSpan, int(span_id[1:]))
        ref = sp.payload_ref if sp else None
    elif span_id.startswith("m") and span_id[1:].isdigit():
        lg = await db.get(LlmCallLog, int(span_id[1:]))
        ref = lg.payload_ref if lg else None
    return load_payload(ref) if ref else None


async def list_runs(
    db: AsyncSession,
    *,
    status: str | None = None,
    flow_key: str | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(AgentRun).order_by(AgentRun.id.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(AgentRun.project_id == project_id)
    if status:
        stmt = stmt.where(AgentRun.status == status)
    if flow_key:
        stmt = stmt.where(AgentRun.flow_key == flow_key)
    runs = (await db.execute(stmt)).scalars().all()
    counts: dict[int, int] = {}
    if runs:
        for rid, n in (
            await db.execute(
                select(AgentStep.run_id, func.count(AgentStep.id))
                .where(AgentStep.run_id.in_([r.id for r in runs]))
                .group_by(AgentStep.run_id)
            )
        ).all():
            counts[rid] = n
    return [{**run_view(r), "step_count": counts.get(r.id, 0)} for r in runs]


async def lineage(db: AsyncSession, artifact_id: int, *, depth: int = 6) -> dict[str, Any] | None:
    """溯源：向上展开来源链（直到采集内容 / 灵感库条目 / 网页），向下列出被谁使用。"""
    root = await db.get(Artifact, artifact_id)
    if root is None:
        return None

    async def up(aid: int, level: int, seen: set[int]) -> list[dict[str, Any]]:
        if level >= depth:
            return []
        out = []
        for ln in (await db.execute(select(ArtifactLink).where(ArtifactLink.artifact_id == aid))).scalars():
            node: dict[str, Any] = {
                "relation": ln.relation,
                "type": ln.target_type,
                "id": ln.target_id,
                "url": ln.target_url,
                "anchor": ln.anchor,
                "target_anchor": ln.target_anchor,
            }
            if ln.target_type == "artifact" and ln.target_id and ln.target_id not in seen:
                a = await db.get(Artifact, ln.target_id)
                if a:
                    node.update({"title": a.title, "kind": a.kind, "version": a.version})
                    node["sources"] = await up(a.id, level + 1, seen | {a.id})
            out.append(node)
        return out

    users = (
        (
            await db.execute(
                select(Artifact)
                .join(ArtifactLink, ArtifactLink.artifact_id == Artifact.id)
                .where(ArtifactLink.target_type == "artifact", ArtifactLink.target_id == artifact_id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "artifact": artifact_view(root),
        "sources": await up(root.id, 0, {root.id}),
        "used_by": [{"id": a.id, "kind": a.kind, "title": a.title, "version": a.version} for a in users],
    }
