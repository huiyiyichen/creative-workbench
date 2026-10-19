"""条目详情（5.6）：今日、热点、报告、专题、灵感库共用。

* 顶部：结论与依据（4.3），可「不对」改成正确的结论；
* 原文 / 视频预览、封面、作者、发布与采集时间；
* 指标与观测曲线；
* 同一事件的其他来源、所属专题；归错时「移出此事件」；
* 角度（完整分析产出）；未分析时「分析并给角度」= 按需补分析（不受每日预算限制，计入花费）；
* 评论状态（评论采集在阶段 3）；
* 经历：从采集到成片的过程（2.3）。
* 事件成员继承代表的分析结果（阶段 1 留下的事项）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AiAnalysis
from app.models.content import ContentItem
from app.models.content_event import ContentEventGroup, ContentEventMember
from app.models.dossier import TopicDossier
from app.models.feedback import FEEDBACK_SCORE_DELTAS, FeedbackType, UserFeedback
from app.services.content_journey import list_journey, record_journey
from app.services.discovery import _series, item_cards
from app.services.verdict_service import mark_verdict, refresh_items

VALID_VERDICTS = ("worth", "watch", "skip")
FEEDBACK_KINDS = {"useful": FeedbackType.like, "not_interested": FeedbackType.not_relevant}


class ItemNotFoundError(LookupError):
    pass


def _angles(analysis: AiAnalysis | None) -> list[dict[str, Any]]:
    raw = analysis.creator_angles if analysis else None
    if not raw:
        return []
    items = raw if isinstance(raw, list) else raw.get("angles") if isinstance(raw, dict) else None
    out = []
    for a in (items or [])[:3]:
        if isinstance(a, str):
            out.append({"title": a, "detail": None})
        elif isinstance(a, dict):
            out.append(
                {
                    "title": a.get("title") or a.get("angle") or a.get("name") or "",
                    "detail": a.get("description") or a.get("detail") or a.get("why"),
                }
            )
    return [a for a in out if a["title"]]


def _analysis_view(analysis: AiAnalysis | None, *, inherited_from: int | None) -> dict[str, Any] | None:
    if analysis is None:
        return None
    return {
        "id": analysis.id,
        "inherited_from": inherited_from,
        "summary": analysis.summary,
        "recommendation": analysis.recommendation,
        "key_points": analysis.key_points,
        "risk_score": analysis.risk_score,
        "risk_notes": analysis.risk_notes,
        "info_density": analysis.info_density,
        "actionability": analysis.actionability,
        "quality_score": analysis.quality_score,
        "tags": analysis.tags,
        "angles": _angles(analysis),
        "title_suggestions": analysis.title_suggestions,
        "created_at": analysis.created_at,
        "final_model": analysis.final_model,
    }


async def _require(db: AsyncSession, content_id: int) -> ContentItem:
    item = await db.get(ContentItem, content_id)
    if item is None:
        raise ItemNotFoundError(f"content {content_id} not found")
    return item


async def _latest_analysis(db: AsyncSession, content_id: int) -> AiAnalysis | None:
    return (
        await db.execute(
            select(AiAnalysis).where(AiAnalysis.content_id == content_id).order_by(AiAnalysis.id.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def _event_block(db: AsyncSession, item: ContentItem) -> dict[str, Any] | None:
    member = (
        await db.execute(
            select(ContentEventMember).where(
                ContentEventMember.content_id == item.id, ContentEventMember.review_status != "rejected"
            )
        )
    ).scalar_one_or_none()
    if member is None:
        return None
    group = await db.get(ContentEventGroup, member.event_group_id)
    if group is None:
        return None
    others = (
        (
            await db.execute(
                select(ContentItem)
                .join(ContentEventMember, ContentEventMember.content_id == ContentItem.id)
                .where(
                    ContentEventMember.event_group_id == group.id,
                    ContentEventMember.review_status != "rejected",
                    ContentItem.id != item.id,
                )
                .order_by(func.coalesce(ContentItem.published_at, ContentItem.crawled_at))
                .limit(30)
            )
        )
        .scalars()
        .all()
    )
    dossier = (
        await db.execute(select(TopicDossier).where(TopicDossier.event_group_id == group.id))
    ).scalar_one_or_none()
    return {
        "id": group.id,
        "representative_id": group.representative_content_id or group.canonical_content_id,
        "is_representative": (group.representative_content_id or group.canonical_content_id) == item.id,
        "relation": member.relation_type,
        "confidence": member.confidence,
        "first_at": group.first_occurrence_at,
        "last_at": group.last_occurrence_at,
        "others": [
            {
                "id": o.id,
                "title": o.title,
                "url": o.url,
                "platform": o.platform,
                "media_type": o.media_type or "article",
                "published_at": o.published_at or o.crawled_at,
            }
            for o in others
        ],
        "dossier": {"id": dossier.id, "title": dossier.title} if dossier else None,
    }


async def get_item_detail(db: AsyncSession, content_id: int) -> dict[str, Any]:
    item = await _require(db, content_id)
    verdict = (await refresh_items(db, [item]))[item.id]
    card = (await item_cards(db, [item]))[0]
    event = await _event_block(db, item)
    analysis = await _latest_analysis(db, item.id)
    inherited_from = None
    if analysis is None and event and not event["is_representative"]:
        analysis = await _latest_analysis(db, event["representative_id"])
        inherited_from = event["representative_id"] if analysis is not None else None
    series = await _series(db, [item.id])
    journey = await list_journey(db, item.id)
    feedback = (
        await db.execute(
            select(UserFeedback.feedback_type)
            .where(UserFeedback.content_id == item.id)
            .order_by(UserFeedback.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    watch_dossiers = []
    if item.source_id:
        d = (
            await db.execute(select(TopicDossier).where(TopicDossier.watch_source_id == item.source_id))
        ).scalar_one_or_none()
        if d:
            watch_dossiers.append({"id": d.id, "title": d.title})
    media = item.media or {}
    await db.commit()
    return {
        **card,
        "raw_content": item.raw_content,
        "summary_full": item.summary,
        "author_url": item.author_url,
        "media": media,
        "tags": item.tags,
        "language": item.language,
        "skip_reason": item.skip_reason,
        "triage_score": item.triage_score,
        "triage_signals": item.triage_signals,
        "quick_result": item.quick_result,
        "full_eligible": item.full_eligible,
        "comment_state": item.comment_state,
        "verdict_full": verdict,
        "series": {m: [{"at": at, "value": v} for at, v in rows] for m, rows in series.get(item.id, {}).items()},
        "event": event,
        "dossiers": ([event["dossier"]] if event and event["dossier"] else []) + watch_dossiers,
        "analysis": _analysis_view(analysis, inherited_from=inherited_from),
        "feedback": {FeedbackType.like: "useful", FeedbackType.not_relevant: "not_interested"}.get(feedback),
        "journey": journey,
    }


async def set_verdict(db: AsyncSession, content_id: int, verdict: str | None, note: str | None) -> dict[str, Any]:
    if verdict is not None and verdict not in VALID_VERDICTS:
        raise ValueError("verdict must be worth / watch / skip")
    item = await _require(db, content_id)
    result = await mark_verdict(db, item, verdict, note)
    if verdict:
        await record_journey(
            db, item.id, "verdict", f"你把结论改为「{result['label']}」", detail={"user_verdict": verdict}
        )
    await db.commit()
    return result


async def set_feedback(db: AsyncSession, content_id: int, kind: str | None, user_id: int) -> dict[str, Any]:
    """「有用 / 不感兴趣」；kind=None 撤销。记入 user_feedback，参与个性化排序。"""
    item = await _require(db, content_id)
    existing = (
        (
            await db.execute(
                select(UserFeedback).where(
                    UserFeedback.content_id == item.id,
                    UserFeedback.feedback_type.in_(list(FEEDBACK_KINDS.values())),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in existing:
        await db.delete(row)
    if kind is not None:
        ftype = FEEDBACK_KINDS.get(kind)
        if ftype is None:
            raise ValueError("kind must be useful / not_interested")
        db.add(
            UserFeedback(
                user_id=user_id,
                content_id=item.id,
                feedback_type=ftype,
                score_delta=FEEDBACK_SCORE_DELTAS[ftype],
            )
        )
    await db.flush()
    verdict = (await refresh_items(db, [item]))[item.id]
    await db.commit()
    return {"feedback": kind, "verdict": verdict}


async def remove_from_event(db: AsyncSession, content_id: int) -> dict[str, Any]:
    """归错时「移出此事件」：成员标为 rejected；若它是分析代表，改选剩余成员里最早的一条。"""
    item = await _require(db, content_id)
    member = (
        await db.execute(
            select(ContentEventMember).where(
                ContentEventMember.content_id == item.id, ContentEventMember.review_status != "rejected"
            )
        )
    ).scalar_one_or_none()
    if member is None:
        return {"removed": False}
    group = await db.get(ContentEventGroup, member.event_group_id)
    member.review_status = "rejected"
    member.reason = "在条目详情中移出此事件"
    member.updated_at = datetime.now(UTC)
    if group is not None:
        remaining = (
            (
                await db.execute(
                    select(ContentItem)
                    .join(ContentEventMember, ContentEventMember.content_id == ContentItem.id)
                    .where(
                        ContentEventMember.event_group_id == group.id,
                        ContentEventMember.review_status != "rejected",
                    )
                    .order_by(func.coalesce(ContentItem.published_at, ContentItem.crawled_at))
                )
            )
            .scalars()
            .all()
        )
        if (group.representative_content_id == item.id or group.canonical_content_id == item.id) and remaining:
            if group.representative_content_id == item.id:
                group.representative_content_id = remaining[0].id
            if group.canonical_content_id == item.id:
                group.canonical_content_id = remaining[0].id
        if len(remaining) <= 1:
            group.status = "archived"
        group.version += 1
    # 移出后自己成为独立条目：恢复进入分析漏斗的资格
    if item.analysis_level != "full" and item.full_eligible is False and (item.quick_result or {}).get("event"):
        item.full_eligible = None
        item.quick_result = None
    await record_journey(
        db, item.id, "event", f"移出事件 #{member.event_group_id}", detail={"event_id": member.event_group_id}
    )
    await db.flush()
    await refresh_items(db, [item])
    await db.commit()
    return {"removed": True, "event_id": member.event_group_id}


async def analyze_now(db: AsyncSession, content_id: int) -> dict[str, Any]:
    """按需补分析（4.1）：点「分析并给角度」、收藏、用作项目来源时调用；不受每日预算限制，计入花费。"""
    from app.services.analysis import analyze_content

    item = await _require(db, content_id)
    if item.analysis_level == "full":
        return {"analyzed": False, "reason": "已完整分析"}
    analysis = await analyze_content(item, db)
    await db.flush()
    await refresh_items(db, [item], record=True)
    await db.commit()
    return {"analyzed": True, "analysis_id": analysis.id}
