"""全局事件流：一个后台循环算一次快照，推给所有打开的页面（取代前端各处的定时轮询）。

主题：
- tasks：任务中心摘要（进行中数量、各状态计数、进行中的条目、刚结束的条目），3 秒检查一次；
- notifications：每个用户的未读通知数，15 秒；
- sources：信源是否有问题（暂停 / 失败 / 可能失效），60 秒。

只在有订阅者时运行；没有变化时不推送（连接上每 15 秒发一次注释心跳）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TASKS_EVERY = 3.0
NOTIFY_EVERY = 15.0
SOURCES_EVERY = 60.0


@dataclass(eq=False)
class Subscriber:
    user_id: int | None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))

    def put(self, event: str, data: Any) -> None:
        try:
            self.queue.put_nowait((event, data))
        except asyncio.QueueFull:  # 页面卡住不读：丢最旧的
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait((event, data))


def finished_between(prev: dict[str, str], items: list[dict]) -> list[dict]:
    """上一轮还在、这一轮状态变成结束 / 等待的条目（用来弹通知）。"""
    return [
        r
        for r in items
        if r["key"] in prev
        and prev[r["key"]] != r["status"]
        and r["status"] in ("done", "failed", "stopped", "waiting")
    ]


def sources_have_problems(rows: list[dict]) -> bool:
    return any(r.get("enabled") and r.get("state") in ("paused", "error", "stale") for r in rows)


class EventHub:
    def __init__(self) -> None:
        self.subs: set[Subscriber] = set()
        self.latest: dict[str, Any] = {}
        self.unread: dict[int, int] = {}
        self._task: asyncio.Task | None = None
        self._last_status: dict[str, str] = {}

    # ── 订阅 ──
    def subscribe(self, user_id: int | None) -> Subscriber:
        sub = Subscriber(user_id)
        self.subs.add(sub)
        for topic in ("tasks", "sources"):
            if topic in self.latest:
                sub.put(topic, self.latest[topic])
        if user_id is not None and user_id in self.unread:
            sub.put("notifications", {"count": self.unread[user_id]})
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="event-hub")
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self.subs.discard(sub)

    def publish(self, topic: str, data: Any, user_id: int | None = None) -> None:
        for s in list(self.subs):
            if user_id is None or s.user_id == user_id:
                s.put(topic, data)

    # ── 采样 ──
    async def tick_tasks(self) -> None:
        from app.core.database import async_session
        from app.services import task_service

        async with async_session() as db:
            data = await task_service.list_tasks(db, days=2, limit=60)
        now = {r["key"]: r["status"] for r in data["items"]}
        if "tasks" in self.latest and now == self._last_status:
            return
        payload = {
            "active": data["active"],
            "counts": data["counts"],
            "items": [r for r in data["items"] if r["status"] in ("running", "waiting")][:20],
            "finished": finished_between(self._last_status, data["items"]) if "tasks" in self.latest else [],
        }
        self._last_status = now
        self.latest["tasks"] = {**payload, "finished": []}  # 新连上的页面不重复弹已结束的通知
        self.publish("tasks", payload)

    async def tick_notifications(self) -> None:
        from app.services import notification_service

        for uid in {s.user_id for s in self.subs if s.user_id is not None}:
            count = await notification_service.get_unread_count(uid)
            if self.unread.get(uid) != count:
                self.unread[uid] = count
                self.publish("notifications", {"count": count}, user_id=uid)

    async def tick_sources(self) -> None:
        from app.core.database import async_session
        from app.services.collection_service import build_health

        async with async_session() as db:
            rows = await build_health(db)
        payload = {"alert": sources_have_problems(rows)}
        if self.latest.get("sources") != payload:
            self.latest["sources"] = payload
            self.publish("sources", payload)

    async def _run(self) -> None:
        due = {"tasks": 0.0, "notifications": 0.0, "sources": 0.0}
        every = {"tasks": TASKS_EVERY, "notifications": NOTIFY_EVERY, "sources": SOURCES_EVERY}
        ticks = {"tasks": self.tick_tasks, "notifications": self.tick_notifications, "sources": self.tick_sources}
        try:
            while self.subs:
                now = time.monotonic()
                for topic, at in due.items():
                    if now >= at:
                        due[topic] = now + every[topic]
                        try:
                            await ticks[topic]()
                        except Exception:  # 单个主题失败不影响其他主题，下一轮再试
                            logger.warning("event hub %s tick failed", topic, exc_info=True)
                await asyncio.sleep(1.0)
        finally:
            # 没人订阅后清掉缓存，下次有人连上时重新采样
            self.latest.clear()
            self.unread.clear()
            self._last_status = {}


hub = EventHub()
