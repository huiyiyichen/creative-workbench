"""Tests for the analyses API endpoints.

Covers:
- P0-1 fix verification: analyze_single error message does not leak internals
- get_analysis returns 404 for non-existent analysis
- list_analyses pagination and score filters
- batch endpoint input validation (empty list, >50 items)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.main  # noqa: F401 - import all models for Base.metadata
from app.api.v1 import analyses as analyses_api, auth as auth_api
from app.core.database import Base
from app.models.content import ContentItem
from app.models.source import Source
from app.services.auth_service import get_local_user

router = analyses_api.router


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """In-memory SQLite + AsyncClient for the local workspace."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await get_local_user(db)
        # Seed a source + content item for tests
        db.add(Source(name="Test", url="https://example.com", source_type="RSS", status="active"))
        await db.flush()
        db.add(
            ContentItem(
                title="Test Article",
                url="https://example.com/article",
                source_id=1,
                source_name="Test",
                source_type="RSS",
                status="crawled",
                content_hash="abc123",
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(analyses_api.router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[auth_api.get_db] = override_get_db
    app.dependency_overrides[analyses_api.get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_single_404_safe_message(api_client: httpx.AsyncClient):
    """P0-1: analyze_single returns 404 with safe message for non-existent content."""
    client = api_client
    resp = await client.post(
        "/analyses/content/99999",
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    # Must not contain internal paths, stack traces, or SQL
    assert "Traceback" not in detail
    assert "sqlalchemy" not in detail.lower()
    assert "/" not in detail or detail.count("/") <= 1  # no file paths


@pytest.mark.asyncio
async def test_get_analysis_404(api_client: httpx.AsyncClient):
    """get_analysis returns 404 for non-existent analysis."""
    client = api_client
    resp = await client.get(
        "/analyses/content/99999",
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Analysis not found"


@pytest.mark.asyncio
async def test_list_analyses_empty(api_client: httpx.AsyncClient):
    """list_analyses returns empty list when no analyses exist."""
    client = api_client
    resp = await client.get(
        "/analyses",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_list_analyses_pagination_params(api_client: httpx.AsyncClient):
    """list_analyses accepts custom page and page_size."""
    client = api_client
    resp = await client.get(
        "/analyses?page=2&page_size=5",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert data["page_size"] == 5


@pytest.mark.asyncio
async def test_list_analyses_score_filters(api_client: httpx.AsyncClient):
    """list_analyses accepts min_creator_score and min_viral_score filters."""
    client = api_client
    resp = await client.get(
        "/analyses?min_creator_score=50&min_viral_score=30",
    )
    assert resp.status_code == 200
    data = resp.json()
    # With no data, still returns valid structure
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_list_analyses_invalid_page(api_client: httpx.AsyncClient):
    """list_analyses rejects page < 1."""
    client = api_client
    resp = await client.get(
        "/analyses?page=0",
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_analyses_invalid_page_size(api_client: httpx.AsyncClient):
    """list_analyses rejects page_size > 100."""
    client = api_client
    resp = await client.get(
        "/analyses?page_size=200",
    )
    assert resp.status_code == 422


@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """In-memory SQLite + AsyncClient for the local workspace."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await get_local_user(db)
        db.add(Source(name="Test", url="https://example.com", source_type="RSS", status="active"))
        await db.flush()
        db.add(
            ContentItem(
                title="Test Article",
                url="https://example.com/article",
                source_id=1,
                source_name="Test",
                source_type="RSS",
                status="crawled",
                content_hash="abc123",
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(analyses_api.router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[auth_api.get_db] = override_get_db
    app.dependency_overrides[analyses_api.get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_empty_list_rejected(admin_client: httpx.AsyncClient):
    """batch endpoint rejects empty content_ids list (admin only)."""
    client = admin_client
    resp = await client.post(
        "/analyses/batch",
        json=[],
    )
    assert resp.status_code == 400
    assert "No content IDs" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_batch_too_many_rejected(admin_client: httpx.AsyncClient):
    """batch endpoint rejects >50 content_ids (admin only)."""
    client = admin_client
    resp = await client.post(
        "/analyses/batch",
        json=list(range(51)),
    )
    assert resp.status_code == 400
    assert "Maximum 50" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_analysis_job_404(api_client: httpx.AsyncClient):
    """get_analysis_job_status returns 404 for non-existent job."""
    client = api_client
    resp = await client.get(
        "/analyses/jobs/nonexistent-job-id",
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Analysis job not found"
