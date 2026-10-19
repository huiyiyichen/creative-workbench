"""发现：今日（5.1）、条目详情（5.6）、热点 · 升温 / 追踪词（5.2）、专题（5.5）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.collection_service import build_overview
from app.services.discovery import (
    mark_today_seen,
    resonance_matrix,
    today_feed,
    today_signals,
    watch_term_panel,
)
from app.services.dossiers import (
    DossierNotFoundError,
    follow_topic,
    get_dossier,
    list_dossiers,
    rising_board,
    set_followed,
    watch_term_curves,
)
from app.services.item_detail import (
    ItemNotFoundError,
    analyze_now,
    get_item_detail,
    remove_from_event,
    set_feedback,
    set_verdict,
)
from app.services.verdict_service import agreement_rate

router = APIRouter(tags=["discover"], dependencies=[Depends(get_current_user)])


# ── 今日 ──


@router.get("/today/feed")
async def get_today_feed(
    view: Literal["all", "picks"] = "all",
    media: str | None = Query(None, max_length=20),
    platform: str | None = Query(None, max_length=50),
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await today_feed(db, view=view, media=media, platform=platform, limit=limit, offset=offset)


@router.get("/today/signals")
async def get_today_signals(db: AsyncSession = Depends(get_db)):
    return await today_signals(db)


@router.get("/today/side")
async def get_today_side(db: AsyncSession = Depends(get_db)):
    overview = await build_overview(db)
    return {
        "watch_terms": await watch_term_panel(db),
        "resonance": await resonance_matrix(db),
        "collection": overview,
    }


@router.post("/today/seen")
async def post_today_seen(db: AsyncSession = Depends(get_db)):
    return await mark_today_seen(db)


# ── 条目详情 ──


class VerdictBody(BaseModel):
    verdict: Literal["worth", "watch", "skip"] | None = None
    note: str | None = Field(None, max_length=500)


class FeedbackBody(BaseModel):
    kind: Literal["useful", "not_interested"] | None = None


@router.get("/items/{content_id}")
async def get_item(content_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await get_item_detail(db, content_id)
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="条目不存在") from exc


@router.put("/items/{content_id}/verdict")
async def put_item_verdict(content_id: int, body: VerdictBody, db: AsyncSession = Depends(get_db)):
    try:
        return await set_verdict(db, content_id, body.verdict, body.note)
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="条目不存在") from exc


@router.put("/items/{content_id}/feedback")
async def put_item_feedback(
    content_id: int,
    body: FeedbackBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await set_feedback(db, content_id, body.kind, user.id)
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="条目不存在") from exc


@router.post("/items/{content_id}/leave-event")
async def post_leave_event(content_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await remove_from_event(db, content_id)
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="条目不存在") from exc


@router.post("/items/{content_id}/analyze")
async def post_analyze_now(content_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await analyze_now(db, content_id)
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="条目不存在") from exc


@router.get("/verdicts/agreement")
async def get_verdict_agreement(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    return await agreement_rate(db, days=days)


# ── 热点 · 升温 / 追踪词 ──


@router.get("/hot/rising")
async def get_rising(
    status: Literal["new", "rising", "steady", "peak", "cooling", "quiet"] | None = None,
    kind: Literal["event", "watch_term"] | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    return await rising_board(db, status=status, kind=kind, limit=limit)


@router.get("/hot/watch-terms")
async def get_watch_terms(db: AsyncSession = Depends(get_db)):
    return {"items": await watch_term_curves(db)}


# ── 专题 ──


class FollowBody(BaseModel):
    event_id: int | None = None
    watch_source_id: int | None = None
    title: str | None = Field(None, max_length=300)
    query: str | None = Field(None, max_length=255)


class FollowedBody(BaseModel):
    followed: bool


@router.get("/dossiers")
async def get_dossiers(
    archived: bool = False, q: str | None = Query(None, max_length=100), db: AsyncSession = Depends(get_db)
):
    return {"items": await list_dossiers(db, archived=archived, q=q)}


@router.post("/dossiers/follow")
async def post_follow(body: FollowBody, db: AsyncSession = Depends(get_db)):
    try:
        d = await follow_topic(
            db, event_id=body.event_id, watch_source_id=body.watch_source_id, title=body.title, query=body.query
        )
    except DossierNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": d.id, "followed": d.followed}


@router.get("/dossiers/{dossier_id}")
async def get_dossier_detail(dossier_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await get_dossier(db, dossier_id)
    except DossierNotFoundError as exc:
        raise HTTPException(status_code=404, detail="专题不存在") from exc


@router.put("/dossiers/{dossier_id}/followed")
async def put_followed(dossier_id: int, body: FollowedBody, db: AsyncSession = Depends(get_db)):
    try:
        d = await set_followed(db, dossier_id, body.followed)
    except DossierNotFoundError as exc:
        raise HTTPException(status_code=404, detail="专题不存在") from exc
    return {"id": d.id, "followed": d.followed}
