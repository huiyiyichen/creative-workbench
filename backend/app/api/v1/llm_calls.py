"""模型调用记录与载荷（改造方案 2.3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.llm_model import LlmCallLog
from app.repositories.llm_call_log_repo import LlmCallTraceRepository
from app.services.trace_payloads import load_payload

router = APIRouter(prefix="/llm-calls", tags=["llm-calls"], dependencies=[Depends(get_current_user)])


def _row(log: LlmCallLog) -> dict:
    return {
        "request_id": log.request_id,
        "scene": log.scene,
        "status": log.status,
        "model": log.actual_model or log.request_model,
        "input_tokens": log.input_tokens,
        "output_tokens": log.output_tokens,
        "total_cost": log.total_cost,
        "duration_ms": log.duration_ms,
        "content_id": log.content_id,
        "run_id": log.run_id,
        "step_id": log.step_id,
        "prompt_summary": log.prompt_summary,
        "response_summary": log.response_summary,
        "has_payload": bool(log.payload_ref),
        "error": log.error_message,
        "at": log.created_at,
    }


@router.get("")
async def list_llm_calls(
    content_id: int | None = None,
    run_id: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    rows = await LlmCallTraceRepository(db).list_calls(content_id=content_id, run_id=run_id, limit=limit)
    return {"items": [_row(r) for r in rows]}


@router.get("/{request_id}/payload")
async def get_llm_call_payload(request_id: str, db: AsyncSession = Depends(get_db)):
    log = await LlmCallTraceRepository(db).get_by_request_id(request_id)
    if log is None or not log.payload_ref:
        raise HTTPException(status_code=404, detail="没有这次调用的载荷")
    payload = load_payload(log.payload_ref)
    if payload is None:
        raise HTTPException(status_code=404, detail="载荷文件已清理或损坏")
    return {"request_id": request_id, "payload": payload}
