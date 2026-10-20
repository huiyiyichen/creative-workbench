"""全局搜索 API：库内检索与按关键词现抓。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services import search_service

router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(get_current_user)])


@router.get("")
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(8, ge=1, le=50),
    groups: str | None = Query(None, description="逗号分隔：contents,library,notes,projects,outputs,reports"),
    db: AsyncSession = Depends(get_db),
):
    wanted = tuple(g for g in (groups or "").split(",") if g in search_service.GROUPS) or None
    try:
        return await search_service.search_all(db, q, limit=limit, groups=wanted)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class CrawlBody(BaseModel):
    q: str = Field(..., min_length=1, max_length=200)
    platforms: list[str] | None = None
    track: bool = False


@router.post("/crawl")
async def crawl(body: CrawlBody, db: AsyncSession = Depends(get_db)):
    try:
        return await search_service.crawl_keyword(db, body.q, platforms=body.platforms, track=body.track)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/platforms")
async def crawl_platforms(db: AsyncSession = Depends(get_db)):
    """可按关键词搜索的平台，以及这个词是否已在追踪。"""
    from app.services.platform_keys import key_status
    from app.services.platforms import ADAPTERS, KEY_ENV
    from app.services.source_registry import searchable_platforms

    keys = await key_status(db)
    return {
        "items": [
            {
                "platform": p,
                "label": ADAPTERS[p].label,
                "needs_key": p in KEY_ENV,
                "has_key": keys.get(p, False),
            }
            for p in searchable_platforms()
        ]
    }


@router.get("/tracking")
async def tracking(q: str = Query(..., min_length=1, max_length=200), db: AsyncSession = Depends(get_db)):
    source = await search_service.find_keyword_source(db, " ".join(q.split()))
    if source is None:
        return {"source_id": None, "tracking": False}
    return {"source_id": source.id, "tracking": bool(source.enabled), "platforms": source.platforms}
