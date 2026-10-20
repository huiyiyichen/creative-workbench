"""全局事件流：一份快照推给所有订阅者，没变化不推，刚结束的任务单独带出。"""

from __future__ import annotations

import asyncio

import pytest

from app.services import event_hub as eh


def test_helpers():
    prev = {"flow:1": "running", "gen:2": "running"}
    items = [
        {"key": "flow:1", "status": "done"},
        {"key": "gen:2", "status": "running"},
        {"key": "new:3", "status": "failed"},
    ]
    assert [r["key"] for r in eh.finished_between(prev, items)] == ["flow:1"]
    assert eh.sources_have_problems([{"enabled": True, "state": "error"}])
    assert not eh.sources_have_problems([{"enabled": False, "state": "error"}, {"enabled": True, "state": "ok"}])


@pytest.mark.asyncio
async def test_hub_publish_and_diff(monkeypatch):
    hub = eh.EventHub()
    calls = {"n": 0}
    snapshots = [
        {"active": 1, "counts": {"running": 1}, "items": [{"key": "flow:1", "status": "running"}]},
        {"active": 1, "counts": {"running": 1}, "items": [{"key": "flow:1", "status": "running"}]},
        {"active": 0, "counts": {"done": 1}, "items": [{"key": "flow:1", "status": "done", "title": "t"}]},
    ]

    async def fake_list(db, days, limit):
        calls["n"] += 1
        return snapshots[min(calls["n"], 3) - 1]

    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    from app.core import database
    from app.services import task_service

    monkeypatch.setattr(task_service, "list_tasks", fake_list)
    monkeypatch.setattr(database, "async_session", lambda: _Ctx())
    # 不启动后台循环，手动驱动
    monkeypatch.setattr(asyncio, "create_task", lambda coro, name=None: (coro.close(), None)[1])
    a = hub.subscribe(1)
    b = hub.subscribe(2)

    await hub.tick_tasks()
    await hub.tick_tasks()  # 没变化：不推
    await hub.tick_tasks()
    got = []
    while not a.queue.empty():
        got.append(a.queue.get_nowait())
    assert [e for e, _ in got] == ["tasks", "tasks"]
    assert got[0][1]["finished"] == []
    assert got[1][1]["active"] == 0 and got[1][1]["finished"][0]["key"] == "flow:1"
    assert b.queue.qsize() == 2

    # 新订阅者立刻拿到最新快照；按用户推送只给那个用户
    c = hub.subscribe(1)
    assert c.queue.get_nowait()[0] == "tasks"
    hub.publish("notifications", {"count": 3}, user_id=2)
    assert b.queue.qsize() == 3 and c.queue.empty()
    hub.unsubscribe(a)
    assert a not in hub.subs


def test_queue_drops_oldest_when_full():
    s = eh.Subscriber(None, asyncio.Queue(maxsize=2))
    for i in range(3):
        s.put("x", i)
    assert [s.queue.get_nowait()[1] for _ in range(2)] == [1, 2]
