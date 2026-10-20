"""运行事件总线（进程内）：流程引擎发布步骤 / 调用 / 状态事件，SSE 端点订阅。

断线重连时 SSE 端点先补发运行快照（见 api ``/runs/{id}/stream``），之后再接实时事件，
所以这里不保存历史，只做扇出。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi.encoders import jsonable_encoder

_subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
_all: set[asyncio.Queue] = set()
MAX_QUEUE = 500


async def publish(run_id: int, event: dict[str, Any]) -> None:
    payload = jsonable_encoder({**event, "run_id": run_id})
    for q in [*_subscribers.get(run_id, ()), *_all]:
        if q.qsize() < MAX_QUEUE:  # 慢消费者丢弃，重连时由快照补齐
            q.put_nowait(payload)


class Subscription:
    """``async with Subscription(run_id) as q:``；run_id=None 订阅全部运行（任务中心）。"""

    def __init__(self, run_id: int | None):
        self.run_id = run_id
        self.queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self) -> asyncio.Queue:
        (_all if self.run_id is None else _subscribers[self.run_id]).add(self.queue)
        return self.queue

    async def __aexit__(self, *exc) -> None:
        if self.run_id is None:
            _all.discard(self.queue)
        else:
            subs = _subscribers.get(self.run_id)
            if subs is not None:
                subs.discard(self.queue)
                if not subs:
                    _subscribers.pop(self.run_id, None)


def subscriber_count(run_id: int) -> int:
    return len(_subscribers.get(run_id, ()))
