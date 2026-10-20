"""全局事件流（SSE）：任务、未读通知、信源告警。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.api.v1.auth import get_current_user
from app.models.user import User
from app.services.event_hub import hub

router = APIRouter(prefix="/events", tags=["events"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
HEARTBEAT = 15.0


def sse_line(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n"


async def hub_stream(request: Request, user_id: int | None, topics: set[str] | None = None):
    sub = hub.subscribe(user_id)
    try:
        yield "retry: 5000\n\n"
        while not await request.is_disconnected():
            try:
                event, data = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if topics is None or event in topics:
                yield sse_line(event, data)
    finally:
        hub.unsubscribe(sub)


@router.get("/stream")
async def events_stream(request: Request, current_user: User = Depends(get_current_user)):
    return StreamingResponse(hub_stream(request, current_user.id), media_type="text/event-stream", headers=_SSE_HEADERS)
