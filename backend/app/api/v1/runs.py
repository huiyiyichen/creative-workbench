"""流程运行（改造方案 2.2 / 2.3）：启动、关卡、继续、停止、重跑；运行视图（节点图 / 时间线 / 调用树）；
SSE 实时事件；溯源；工作台工具与 MCP 端点。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services import run_events, trace_service, workbench_tools as wt
from app.services.flows import engine
from app.services.run_export import run_markdown

router = APIRouter(tags=["runs"], dependencies=[Depends(get_current_user)])
# MCP 端点由外部 agent 调用，按工作台令牌鉴权，不走登录态
mcp_router = APIRouter(tags=["mcp"])


def _bad(exc: Exception, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


class StartBody(BaseModel):
    flow_key: str = "topic_research"
    inputs: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    gates: dict[str, bool] | None = None
    budget: dict[str, float] | None = None
    project_id: int | None = Field(default=None, gt=0)


class GateBody(BaseModel):
    card_id: str | None = None
    custom: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)


class ContinueBody(BaseModel):
    cost: float | None = Field(default=None, ge=0)
    steps: int | None = Field(default=None, ge=0)
    seconds: int | None = Field(default=None, ge=0)


class ForkBody(BaseModel):
    node: str
    prompt_extra: str | None = Field(default=None, max_length=2000)
    routing_group: str | None = Field(default=None, max_length=50)
    executor: Literal["internal", "deepseek_harness", "claude_code", "codex"] | None = None


class TokenBody(BaseModel):
    label: str = Field(default="外部 agent", max_length=100)
    tools: list[str] | None = None
    ttl_hours: float | None = Field(default=24, ge=0)


@router.get("/flows")
async def list_flows():
    return {"items": engine.flows_catalog()}


@router.get("/runs")
async def list_runs(
    status: str | None = None,
    flow_key: str | None = None,
    project_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    return {
        "items": await trace_service.list_runs(db, status=status, flow_key=flow_key, project_id=project_id, limit=limit)
    }


@router.post("/runs")
async def start_run(body: StartBody, db: AsyncSession = Depends(get_db)):
    try:
        run = await engine.start_run(
            db,
            body.flow_key,
            body.inputs,
            title=body.title,
            gates=body.gates,
            budget=body.budget,
            project_id=body.project_id,
        )
    except engine.FlowError as exc:
        raise _bad(exc) from exc
    return trace_service.run_view(run)


@router.get("/runs/stream")
async def stream_all(request: Request):
    """任务中心：所有运行的状态变化。"""
    return StreamingResponse(_sse(request, None, None), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/runs/spans/{span_id}/payload")
async def span_payload(span_id: str, db: AsyncSession = Depends(get_db)):
    data = await trace_service.span_payload(db, span_id)
    if data is None:
        raise HTTPException(status_code=404, detail="没有载荷（可能已清理）")
    return data


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    data = await trace_service.run_detail(db, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return data


@router.get("/runs/{run_id}/trace")
async def get_trace(run_id: int, db: AsyncSession = Depends(get_db)):
    return {"items": await trace_service.trace_tree(db, run_id)}


@router.get("/runs/{run_id}/steps/{step_id}")
async def get_step(run_id: int, step_id: int, db: AsyncSession = Depends(get_db)):
    data = await trace_service.step_detail(db, step_id)
    if data is None or data["run_id"] != run_id:
        raise HTTPException(status_code=404, detail="步骤不存在")
    return data


@router.post("/runs/{run_id}/gate")
async def resolve_gate(run_id: int, body: GateBody, db: AsyncSession = Depends(get_db)):
    try:
        run = await engine.resume_gate(db, run_id, body.model_dump(exclude_none=True))
    except engine.FlowError as exc:
        raise _bad(exc) from exc
    return trace_service.run_view(run)


@router.post("/runs/{run_id}/continue")
async def continue_run(run_id: int, body: ContinueBody, db: AsyncSession = Depends(get_db)):
    try:
        run = await engine.continue_run(db, run_id, body.model_dump(exclude_none=True))
    except engine.FlowError as exc:
        raise _bad(exc) from exc
    return trace_service.run_view(run)


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: int, db: AsyncSession = Depends(get_db)):
    try:
        run = await engine.stop_run(db, run_id)
    except engine.FlowError as exc:
        raise _bad(exc, 404) from exc
    return trace_service.run_view(run)


@router.post("/runs/{run_id}/fork")
async def fork_run(run_id: int, body: ForkBody, db: AsyncSession = Depends(get_db)):
    try:
        run = await engine.fork_run(
            db, run_id, body.node, {"prompt_extra": body.prompt_extra, "routing_group": body.routing_group, "executor": body.executor}
        )
    except engine.FlowError as exc:
        raise _bad(exc) from exc
    return trace_service.run_view(run)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: int, format: str = Query("json", pattern="^(json|md)$"), db: AsyncSession = Depends(get_db)
):
    data = await trace_service.run_detail(db, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    data["trace"] = await trace_service.trace_tree(db, run_id)
    name = f"run-{run_id}"
    if format == "md":
        return PlainTextResponse(
            run_markdown(data),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.md"'},
        )
    return Response(
        json.dumps(jsonable_encoder(data), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}.json"'},
    )


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """运行视图实时更新：先补发快照（断线重连补齐），再推送步骤 / 调用 / 状态事件。"""
    snapshot = await trace_service.run_detail(db, run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return StreamingResponse(_sse(request, run_id, snapshot), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/artifacts/{artifact_id}/lineage")
async def artifact_lineage(artifact_id: int, anchor: str | None = None, db: AsyncSession = Depends(get_db)):
    data = await trace_service.lineage(db, artifact_id, anchor=anchor)
    if data is None:
        raise HTTPException(status_code=404, detail="产物不存在")
    return data


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def _sse(request: Request, run_id: int | None, snapshot: dict[str, Any] | None):
    def pack(event: str, data: Any) -> str:
        return f"event: {event}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n"

    async with run_events.Subscription(run_id) as queue:
        if snapshot is not None:
            yield pack("snapshot", snapshot)
        while True:
            if await request.is_disconnected():
                break
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            yield pack(ev.get("type", "message"), ev)


# ── 工作台工具 ──


@router.get("/workbench/tools")
async def workbench_tools():
    return {"items": wt.describe_tools(), "mcp_path": "/api/v1/mcp"}


@router.get("/workbench/tokens")
async def workbench_tokens(db: AsyncSession = Depends(get_db)):
    return {"items": await wt.list_tokens(db)}


@router.post("/workbench/tokens")
async def create_token(body: TokenBody, db: AsyncSession = Depends(get_db)):
    try:
        raw, tok = await wt.issue_token(db, body.label, tools=body.tools, ttl_hours=body.ttl_hours or None)
    except wt.ToolError as exc:
        raise _bad(exc) from exc
    return {**wt.token_view(tok), "token": raw}


@router.delete("/workbench/tokens/{token_id}")
async def revoke_token(token_id: int, db: AsyncSession = Depends(get_db)):
    if not await wt.revoke_token(db, token_id):
        raise HTTPException(status_code=404, detail="令牌不存在")
    return {"revoked": True}


@mcp_router.post("/mcp")
async def mcp_endpoint(
    request: Request, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
):
    """MCP Streamable HTTP（JSON 响应）：initialize / tools/list / tools/call。"""
    raw = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON 解析失败"}})
    messages = body if isinstance(body, list) else [body]
    replies = [r for r in [await wt.handle_mcp(db, raw, m) for m in messages if isinstance(m, dict)] if r is not None]
    if not replies:
        return Response(status_code=202)
    if any(r.get("error", {}).get("code") == -32001 for r in replies) and len(replies) == 1:
        return JSONResponse(jsonable_encoder(replies[0]), status_code=401)
    return JSONResponse(jsonable_encoder(replies if isinstance(body, list) else replies[0]))


@mcp_router.get("/mcp")
async def mcp_get():
    return Response(status_code=405, headers={"Allow": "POST"})


@router.get("/lineage")
async def resolve_lineage(
    target: str,
    project_id: int | None = None,
    version: int | None = None,
    anchor: str | None = None,
    output_id: int | None = None,
    studio_artifact_id: int | None = None,
    shot: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """界面溯源入口（段落 / 版本 / 分镜 / 成片 / 平台稿）→ 溯源树。"""
    from app.services import project_lineage

    art, anc = await project_lineage.resolve(
        db,
        target=target,
        project_id=project_id,
        version=version,
        anchor=anchor,
        output_id=output_id,
        studio_artifact_id=studio_artifact_id,
        shot=shot,
    )
    return await trace_service.lineage(db, art.id, anchor=anc)
