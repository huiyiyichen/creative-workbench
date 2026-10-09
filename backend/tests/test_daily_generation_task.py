from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1 import daily_reports as routes
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.daily_report import DailyReport
from app.models.user import User
from app.services import daily_report as service


@pytest_asyncio.fixture
async def report_client(monkeypatch):
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(email="report-test@local.invalid", role="admin", plan="local")
        db.add(owner)
        await db.commit()

    async def database():
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: owner
    monkeypatch.setattr(routes, "async_session", factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, owner
    await engine.dispose()


async def terminal_result(client, report_id):
    for _ in range(100):
        response = await client.get(f"/daily-reports/generation/{report_id}")
        assert response.status_code == 200
        result = response.json()
        if result["status"] in {"DONE", "ERROR"}:
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("Generation did not terminate on the returned record")


@pytest.mark.asyncio
async def test_empty_input_updates_returned_id_without_creating_another_report(report_client, monkeypatch):
    client, factory, _ = report_client

    async def empty_input(*_args, **_kwargs):
        return [], []

    monkeypatch.setattr(service, "_fetch_report_inputs", empty_input)
    response = await client.post(
        "/daily-reports/generate-version",
        params={"target_date": "2026-10-03", "edition": "manual", "cutoff_at": "2026-10-03T12:30:00+08:00"},
    )
    assert response.status_code == 202
    report_id = response.json()["id"]
    result = await terminal_result(client, report_id)
    assert result["id"] == report_id
    assert result["status"] == "ERROR"
    assert "AI 模型尚未配置" in result["overview"]
    assert result["window_start"] == "2026-10-02T16:00:00Z"
    assert result["window_end"] == result["cutoff_at"] == "2026-10-03T04:30:00Z"
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(DailyReport)) == 1


@pytest.mark.asyncio
async def test_background_failure_marks_the_same_placeholder(report_client, monkeypatch):
    client, _, _ = report_client

    async def failed_input(*_args, **_kwargs):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(service, "_fetch_report_inputs", failed_input)
    response = await client.post("/daily-reports/generate-version", params={"edition": "manual"})
    assert response.status_code == 202
    result = await terminal_result(client, response.json()["id"])
    assert result["status"] == "ERROR"
    assert result["overview"] == "日报生成失败，请检查模型配置后重试。"


@pytest.mark.asyncio
async def test_completed_report_uses_returned_record(report_client, monkeypatch):
    client, _, _ = report_client

    async def analyzed_but_not_selected(*_args, **_kwargs):
        return [], [{"id": 1}]

    monkeypatch.setattr(service, "_fetch_report_inputs", analyzed_but_not_selected)
    response = await client.post("/daily-reports/generate-version", params={"edition": "manual"})
    result = await terminal_result(client, response.json()["id"])
    assert result["status"] == "DONE"
    assert result["top_picks"] == []


@pytest.mark.asyncio
async def test_no_model_is_explicit_even_when_selected_input_exists(report_client, monkeypatch):
    client, _, _ = report_client

    async def selected_input(*_args, **_kwargs):
        return [{"id": 1}], [{"id": 1}]

    monkeypatch.setattr(service, "_fetch_report_inputs", selected_input)
    response = await client.post("/daily-reports/generate-version", params={"edition": "manual"})
    result = await terminal_result(client, response.json()["id"])
    assert result["status"] == "ERROR"
    assert "AI 模型尚未配置" in result["overview"]


@pytest.mark.asyncio
async def test_mine_scope_is_preserved_and_other_owner_status_is_hidden(report_client, monkeypatch):
    client, factory, owner = report_client

    async def empty_input(*_args, **kwargs):
        assert kwargs["visible_user_id"] == owner.id
        return [], []

    monkeypatch.setattr(service, "_fetch_report_inputs", empty_input)
    response = await client.post("/daily-reports/generate-version", params={"edition": "manual", "scope": "mine"})
    result = await terminal_result(client, response.json()["id"])
    assert result["owner_user_id"] == owner.id
    async with factory() as db:
        other = User(email="other-report-test@local.invalid")
        db.add(other)
        await db.flush()
        hidden = DailyReport(owner_user_id=other.id, report_date="2026-10-03", weekday="周六", status="DONE")
        db.add(hidden)
        await db.commit()
    assert (await client.get(f"/daily-reports/generation/{hidden.id}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("parameters", [
    {"target_date": "not-a-date"},
    {"cutoff_at": "not-a-time"},
    {"edition": "unknown"},
])
async def test_invalid_generation_parameters_do_not_create_placeholders(report_client, parameters):
    client, factory, _ = report_client
    assert (await client.post("/daily-reports/generate-version", params=parameters)).status_code == 422
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(DailyReport)) == 0


@pytest.mark.asyncio
async def test_stale_generation_is_reported_as_interrupted_instead_of_waiting_forever(report_client, monkeypatch):
    client, factory, _ = report_client
    monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 10, 3, 12, 30))
    async with factory() as db:
        report = DailyReport(
            report_date="2026-10-03",
            weekday="周六",
            status="GENERATING",
            generated_at=datetime(2026, 10, 3, 4, 0, tzinfo=UTC),
            cutoff_at=datetime(2026, 10, 3, 4, 30, tzinfo=UTC),
        )
        db.add(report)
        await db.commit()
    result = (await client.get("/daily-reports/today")).json()
    assert result["id"] == report.id
    assert result["status"] == "ERROR"
    assert result["overview"] == "上次日报生成已中断，请重新生成。"
