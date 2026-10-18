"""内容经历（改造方案 2.3）：每条内容从采集到成片的每一步。写入失败不影响主链路。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_observation import ContentJourney
from app.repositories.content_journey_repo import ContentJourneyRepository

logger = logging.getLogger(__name__)


async def record_journey(
    db: AsyncSession,
    content_id: int,
    stage: str,
    summary: str | None = None,
    *,
    detail: dict[str, Any] | None = None,
    sync_run_id: int | None = None,
    llm_request_id: str | None = None,
    agent_run_id: str | None = None,
) -> None:
    try:
        async with db.begin_nested():
            await ContentJourneyRepository(db).add(
                ContentJourney(
                    content_id=content_id,
                    stage=stage,
                    summary=summary,
                    detail=detail,
                    sync_run_id=sync_run_id,
                    llm_request_id=llm_request_id,
                    agent_run_id=agent_run_id,
                )
            )
    except Exception:
        logger.debug("journey not recorded for content %s/%s", content_id, stage, exc_info=True)


async def list_journey(db: AsyncSession, content_id: int) -> list[dict[str, Any]]:
    rows = await ContentJourneyRepository(db).list_for_content(content_id)
    return [
        {
            "id": r.id,
            "stage": r.stage,
            "summary": r.summary,
            "detail": r.detail,
            "sync_run_id": r.sync_run_id,
            "llm_request_id": r.llm_request_id,
            "agent_run_id": r.agent_run_id,
            "at": r.created_at,
        }
        for r in rows
    ]
