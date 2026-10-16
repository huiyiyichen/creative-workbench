from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.main  # noqa: F401 - import all models for Base.metadata
from app.api.v1 import auth as auth_api, contents as contents_api
from app.core.database import Base
from app.models.analysis import AiAnalysis
from app.models.content import ContentItem, ContentStatus
from app.repositories.analysis_repo import AnalysisRepository
from app.services import enricher
from app.services.auth_service import get_local_user


@pytest.mark.asyncio
async def test_single_enrich_skips_llm_when_claim_lost(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await get_local_user(db)
        db.add(
            ContentItem(
                id=1,
                title="增强认领失败样本",
                url="https://example.com/content-enrichment-claim-lost",
                source_name="测试信源",
                source_type="RSS",
                status=ContentStatus.ANALYZED,
            )
        )
        db.add(
            AiAnalysis(
                content_id=1,
                summary="测试摘要",
                curation_score=88,
                enrichment_status="pending",
            )
        )
        await db.commit()

    async def fake_claim(_repo: AnalysisRepository, content_id: int):
        return None

    async def fail_if_enrich_runs(content_id: int, db: AsyncSession):
        raise AssertionError("lost enrichment claim should not call LLM")

    monkeypatch.setattr(AnalysisRepository, "claim_enrichment_for_content", fake_claim)
    monkeypatch.setattr(enricher, "enrich_content", fail_if_enrich_runs)

    app = FastAPI()
    app.include_router(contents_api.router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[auth_api.get_db] = override_get_db
    app.dependency_overrides[contents_api.get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/contents/1/enrich",
        )

    assert response.status_code == 200
    assert response.json() == {"content_id": 1, "status": "processing", "enrichment": None}
    await engine.dispose()


@pytest.mark.asyncio
async def test_single_enrich_failure_persists_error_status(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await get_local_user(db)
        db.add(
            ContentItem(
                id=1,
                title="增强失败样本",
                url="https://example.com/content-enrichment-error",
                source_name="测试信源",
                source_type="RSS",
                status=ContentStatus.ANALYZED,
            )
        )
        db.add(
            AiAnalysis(
                id=1,
                content_id=1,
                summary="测试摘要",
                curation_score=88,
                enrichment_status="pending",
            )
        )
        await db.commit()

    async def failing_enrich_content(content_id: int, db: AsyncSession):
        raise RuntimeError("temporary enrichment failure")

    monkeypatch.setattr(enricher, "enrich_content", failing_enrich_content)

    app = FastAPI()
    app.include_router(contents_api.router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[auth_api.get_db] = override_get_db
    app.dependency_overrides[contents_api.get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/contents/1/enrich",
        )

    async with session_factory() as db:
        analysis = await db.get(AiAnalysis, 1)

    assert response.status_code == 500
    assert analysis.enrichment_status == "error"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ignore_actions_use_sqlite_lock_retry(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await get_local_user(db)
        db.add(
            ContentItem(
                id=1,
                title="内容忽略重试样本",
                url="https://example.com/content-ignore-retry",
                source_name="测试信源",
                source_type="RSS",
                status=ContentStatus.ANALYZED,
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(contents_api.router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[auth_api.get_db] = override_get_db
    app.dependency_overrides[contents_api.get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        ignored = await client.post(
            "/contents/1/ignore?reason=seen",
        )
        assert ignored.status_code == 200

        unignored = await client.delete(
            "/contents/1/ignore",
        )
        assert unignored.status_code == 200

    await engine.dispose()


# ── T1-4: content owner_user_id visibility ─────────────────────────────
