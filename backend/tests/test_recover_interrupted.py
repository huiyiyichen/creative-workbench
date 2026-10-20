"""重启恢复：排队中的生图任务重新开跑，运行中的标失败可重试；飞书待写记录标失败。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.feishu import FeishuRecord
from app.models.generation import GenerationJob
from app.services import feishu_service, generation_service


@pytest.mark.asyncio
async def test_recover(test_session_factory, monkeypatch):
    started = []

    async def fake_bg(job_id):
        started.append(job_id)

    monkeypatch.setattr(generation_service, "_session", test_session_factory)
    monkeypatch.setattr(feishu_service, "_session", test_session_factory)
    monkeypatch.setattr(generation_service, "_run_job_bg", fake_bg)
    async with test_session_factory() as db:
        q = GenerationJob(kind="image", prompt="a", status="queued")
        r = GenerationJob(kind="image", prompt="b", status="running")
        d = GenerationJob(kind="image", prompt="c", status="done")
        db.add_all([q, r, d])
        db.add(FeishuRecord(object_type="content", object_id=1, app_token="t", table_id="x", status="pending"))
        db.add(FeishuRecord(object_type="content", object_id=2, app_token="t", table_id="x", status="synced"))
        await db.commit()
    res = await generation_service.recover_interrupted()
    assert res == {"requeued": 1, "failed": 1}
    for t in list(generation_service._tasks.values()):
        await t
    assert started == [q.id]
    assert await feishu_service.recover_interrupted() == 1
    async with test_session_factory() as db:
        assert (await db.get(GenerationJob, r.id)).status == "failed"
        assert (await db.get(GenerationJob, d.id)).status == "done"
        rows = (await db.execute(select(FeishuRecord.status).order_by(FeishuRecord.object_id))).scalars().all()
        assert rows == ["failed", "synced"]
