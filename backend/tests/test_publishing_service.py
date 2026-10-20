"""发布排期、提醒、数据回收与效果汇总。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ValidationError
from app.models.project import ProjectOutput
from app.schemas.projects import ProjectCreate
from app.services import project_service as ps, publishing_service as pub


def test_next_check_cadence():
    p = datetime(2026, 10, 1, tzinfo=UTC)
    assert pub.next_check(p, None) == p
    assert pub.next_check(p, p + timedelta(hours=1)) == p + timedelta(hours=4)
    assert pub.next_check(p, p + timedelta(days=3)) == p + timedelta(days=3, hours=12)
    assert pub.next_check(p, p + timedelta(days=20)) == p + timedelta(days=23)
    assert pub.next_check(p, p + timedelta(days=91)) is None
    assert pub.next_check(None, None) is None


async def _outputs(db):
    proj = await ps.create_project(db, 1, ProjectCreate(theme="发布测试"))
    pid = proj["id"] if isinstance(proj, dict) else proj.id
    a = ProjectOutput(project_id=pid, kind="xhs", title="小红书版", status="done")
    b = ProjectOutput(
        project_id=pid,
        kind="video",
        title="讲解视频",
        status="published",
        published_url="https://www.bilibili.com/video/BV1xx411c7mD",
        published_at=datetime(2026, 10, 20, 2, tzinfo=UTC),
    )
    c = ProjectOutput(project_id=pid, kind="wechat", title="公众号版", status="exported")
    db.add_all([a, b, c])
    await db.commit()
    return a, b, c


@pytest.mark.asyncio
async def test_schedule_calendar_and_remind(test_session_factory, monkeypatch):
    sent = []

    async def fake_push(*args, **kwargs):
        sent.append(args)
        return []

    from app.services import notification_service

    monkeypatch.setattr(notification_service, "push_notification", fake_push)
    async with test_session_factory() as db:
        a, b, c = await _outputs(db)
        at = datetime(2026, 10, 21, 12, tzinfo=UTC)
        r = await pub.set_schedule(db, a.id, at=at, platform="xiaohongshu", note="晚上发")
        assert r["schedule"]["platform"] == "xiaohongshu"
        with pytest.raises(ValidationError):
            await pub.set_schedule(db, b.id, at=at)

        cal = await pub.calendar(db, datetime(2026, 10, 19, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC))
        assert [i["id"] for i in cal["items"]] == [b.id, a.id]
        assert cal["items"][1]["kind_label"] == "小红书"
        assert [i["id"] for i in cal["backlog"]] == [c.id]

        assert await pub.remind_due(db, now=at - timedelta(minutes=1)) == 0
        assert await pub.remind_due(db, now=at + timedelta(minutes=1)) == 1
        assert await pub.remind_due(db, now=at + timedelta(hours=1)) == 0  # 只提醒一次
        assert sent and sent[0][2] == "该发布了"

        await pub.set_schedule(db, a.id, at=None)
        await db.refresh(a)
        assert "schedule" not in a.settings


@pytest.mark.asyncio
async def test_refresh_metrics_and_performance(test_session_factory):
    calls = []

    async def fetch(db, url):
        calls.append(url)
        return {"title": "x", "metrics": {"views": 1000 * len(calls), "likes": 50, "bad": "n/a"}}

    async def broken(db, url):
        raise RuntimeError("限流")

    async with test_session_factory() as db:
        a, b, c = await _outputs(db)
        with pytest.raises(ValidationError):
            await pub.refresh_metrics(db, a.id, fetch=fetch)
        now = datetime(2026, 10, 21, tzinfo=UTC)
        assert await pub.refresh_due(db, now=now, fetch=fetch) == 1
        assert await pub.refresh_due(db, now=now + timedelta(hours=1), fetch=fetch) == 0  # 发布 2 天内每 3 小时一次
        r = await pub.refresh_metrics(db, b.id, fetch=fetch, now=now + timedelta(hours=4))
        assert r["metrics"]["latest"]["views"] == 2000.0 and "bad" not in r["metrics"]["latest"]
        r = await pub.refresh_metrics(db, b.id, fetch=broken, now=now + timedelta(hours=5))
        assert r["metrics"]["error"] == "限流" and r["metrics"]["latest"]["views"] == 2000.0

        series = await pub.metric_series(db, b.id)
        assert [p["value"] for p in series["views"]] == [1000.0, 2000.0]

        perf = await pub.performance(db)
        assert perf["published"] == 1 and perf["tracked"] == 1
        assert perf["by_kind"][0]["label"] == "讲解视频"
        assert perf["by_kind"][0]["median"]["views"] == 2000.0
        assert perf["by_platform"][0]["label"] == "B站"
        assert perf["top"][0]["id"] == b.id
