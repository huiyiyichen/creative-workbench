"""选题结论的取数与刷新（4.3）。

``refresh_verdicts`` 批量为近 7 天的条目收集依据、计算结论并写回 ``content_items.verdict / verdict_data``；
调度器每 15 分钟跑一次，条目详情打开时单条刷新。用户的「不对」（``verdict_marks``）优先于计算结果显示，
但计算结果照常保存，用于一致率。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AiAnalysis
from app.models.content import ContentItem
from app.models.content_observation import ContentJourney, ContentMetricObservation
from app.models.dossier import VerdictMark
from app.models.favorite import FavoriteItem
from app.models.feedback import UserFeedback
from app.services.event_members import event_members_subquery
from app.services.topic_signals import latest_status_for_events
from app.services.verdict import VERDICT_LABEL, VerdictFacts, compute_verdict

REFRESH_WINDOW_DAYS = 7
SIMILAR_FAVORITE = 0.75  # 初筛「与收藏的相似度」≥ 此值算「相关收藏」

_em = event_members_subquery()


async def _latest_metrics(db: AsyncSession, ids: list[int]) -> dict[int, dict[str, list[tuple[datetime, float]]]]:
    rows = (
        await db.execute(
            select(
                ContentMetricObservation.content_id,
                ContentMetricObservation.metric,
                ContentMetricObservation.observed_at,
                ContentMetricObservation.value,
            )
            .where(ContentMetricObservation.content_id.in_(ids))
            .order_by(ContentMetricObservation.observed_at)
        )
    ).all()
    out: dict[int, dict[str, list[tuple[datetime, float]]]] = defaultdict(lambda: defaultdict(list))
    for cid, metric, at, value in rows:
        out[cid][metric].append((at, float(value)))
    return out


async def _events(db: AsyncSession, ids: list[int]) -> tuple[dict[int, int], dict[int, list[tuple[int, str | None]]]]:
    rows = (await db.execute(select(_em.c.content_id, _em.c.event_group_id).where(_em.c.content_id.in_(ids)))).all()
    event_of = dict(rows)
    if not event_of:
        return {}, {}
    members = (
        await db.execute(
            select(_em.c.event_group_id, ContentItem.id, ContentItem.platform)
            .join(ContentItem, ContentItem.id == _em.c.content_id)
            .where(
                _em.c.event_group_id.in_(set(event_of.values())),
            )
        )
    ).all()
    by_event: dict[int, list[tuple[int, str | None]]] = defaultdict(list)
    for gid, cid, platform in members:
        by_event[gid].append((cid, platform))
    return event_of, by_event


async def _favorited(db: AsyncSession, ids: set[int]) -> set[int]:
    if not ids:
        return set()
    rows = (
        await db.execute(
            select(FavoriteItem.target_id).where(FavoriteItem.target_type == "content", FavoriteItem.target_id.in_(ids))
        )
    ).scalars()
    fav = {int(x) for x in rows if x is not None}
    rows2 = (
        await db.execute(select(ContentItem.id).where(ContentItem.id.in_(ids), ContentItem.is_favorited.is_(True)))
    ).scalars()
    return fav | set(rows2)


async def _feedback(db: AsyncSession, ids: list[int]) -> dict[int, str]:
    rows = (
        await db.execute(
            select(UserFeedback.content_id, UserFeedback.feedback_type)
            .where(UserFeedback.content_id.in_(ids))
            .order_by(UserFeedback.created_at)
        )
    ).all()
    return {cid: str(ft) for cid, ft in rows}


async def _analyses(db: AsyncSession, ids: list[int]) -> dict[int, AiAnalysis]:
    latest = (
        select(AiAnalysis.content_id, func.max(AiAnalysis.id).label("id"))
        .where(AiAnalysis.content_id.in_(ids))
        .group_by(AiAnalysis.content_id)
        .subquery()
    )
    rows = (await db.execute(select(AiAnalysis).join(latest, AiAnalysis.id == latest.c.id))).scalars().all()
    return {a.content_id: a for a in rows}


async def _marks(db: AsyncSession, ids: list[int]) -> dict[int, VerdictMark]:
    rows = (await db.execute(select(VerdictMark).where(VerdictMark.content_id.in_(ids)))).scalars().all()
    return {m.content_id: m for m in rows}


def _risk_notes(analysis: AiAnalysis | None) -> list[str]:
    notes = analysis.risk_notes if analysis else None
    if isinstance(notes, list):
        return [str(n) for n in notes if n]
    if isinstance(notes, dict):
        return [str(v) for v in notes.values() if v]
    return []


async def gather_facts(db: AsyncSession, items: list[ContentItem]) -> dict[int, VerdictFacts]:
    ids = [c.id for c in items]
    if not ids:
        return {}
    metrics = await _latest_metrics(db, ids)
    event_of, by_event = await _events(db, ids)
    statuses = await latest_status_for_events(db, list(set(event_of.values())))
    member_ids = {cid for members in by_event.values() for cid, _ in members}
    favorited = await _favorited(db, member_ids | set(ids))
    feedback = await _feedback(db, ids)
    analyses = await _analyses(db, ids)

    facts: dict[int, VerdictFacts] = {}
    for c in items:
        series = metrics.get(c.id, {})
        latest = {m: rows[-1][1] for m, rows in series.items() if rows and m != "rank"}
        rank = series["rank"][-1][1] if series.get("rank") else None
        growth = None
        for key in ("views", "stars", "score", "hot", "likes"):
            rows = series.get(key) or []
            if len(rows) >= 2:
                hours = (rows[-1][0] - rows[0][0]).total_seconds() / 3600
                growth = (key, rows[0][1], rows[-1][1], hours)
                break
        gid = event_of.get(c.id)
        members = by_event.get(gid, []) if gid else []
        signals = c.triage_signals or {}
        related = len([cid for cid, _ in members if cid != c.id and cid in favorited])
        if (signals.get("similarity") or 0) >= SIMILAR_FAVORITE:
            related += 1
        analysis = analyses.get(c.id)
        quality = None
        if analysis is not None and c.analysis_level == "full":
            parts = [
                v for v in (analysis.info_density, analysis.actionability, analysis.quality_score) if v is not None
            ]
            quality = sum(parts) / len(parts) if parts else None
        facts[c.id] = VerdictFacts(
            title=c.title,
            platform=c.platform,
            media_type=c.media_type,
            published_at=c.published_at,
            crawled_at=c.crawled_at,
            metrics=latest,
            growth=growth,
            rank=rank,
            is_rss=(str(c.source_type or "").lower() == "rss"),
            event_id=gid,
            event_members=len(members),
            event_platforms=[p or "web" for _, p in members],
            topic_status=statuses.get(gid) if gid else None,
            keyword_hits=list(signals.get("keyword_hits") or []),
            related_favorites=related,
            feedback=feedback.get(c.id),
            analysis_level=c.analysis_level,
            quick_worth=(c.quick_result or {}).get("worth") if c.quick_result else None,
            risk_score=analysis.risk_score if analysis is not None and c.analysis_level == "full" else None,
            quality=quality,
            risk_notes=_risk_notes(analysis),
            comment_state=c.comment_state,
        )
    return facts


def _with_mark(data: dict[str, Any], mark: VerdictMark | None) -> dict[str, Any]:
    if mark is None:
        return {**data, "user_verdict": None}
    return {
        **data,
        "computed": data["verdict"],
        "verdict": mark.user_verdict,
        "label": VERDICT_LABEL.get(mark.user_verdict, mark.user_verdict),
        "user_verdict": mark.user_verdict,
        "user_note": mark.note,
    }


async def refresh_items(
    db: AsyncSession, items: list[ContentItem], *, record: bool = False
) -> dict[int, dict[str, Any]]:
    """计算并写回；返回 content_id → 结论（已叠加「不对」的人工结论）。"""
    if not items:
        return {}
    from app.services.scoring_settings import load_rules

    facts = await gather_facts(db, items)
    marks = await _marks(db, [c.id for c in items])
    rules = await load_rules(db, "verdict_rules")
    now = datetime.now(UTC)
    out: dict[int, dict[str, Any]] = {}
    became_worth: list[int] = []
    for c in items:
        result = compute_verdict(facts[c.id], now=now, rules=rules).as_dict()
        changed = c.verdict != result["verdict"]
        if changed and result["verdict"] == "worth":
            became_worth.append(c.id)
        c.verdict = result["verdict"]
        c.verdict_data = result
        c.verdict_at = now
        if record and changed:
            db.add(
                ContentJourney(
                    content_id=c.id,
                    stage="verdict",
                    summary=f"结论：{result['label']}。{result['reason']}",
                    detail={"verdict": result["verdict"], "points": result["detail"]["points"]},
                )
            )
        out[c.id] = _with_mark(result, marks.get(c.id))
    await db.flush()
    if became_worth:
        from app.services import feishu_service

        try:  # 可选：结论为「值得做」时自动记入飞书
            await feishu_service.on_verdicts(db, became_worth)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("feishu verdict hook failed", exc_info=True)
    return out


async def refresh_verdicts(db: AsyncSession, *, limit: int = 2000) -> dict[str, int]:
    since = datetime.now(UTC) - timedelta(days=REFRESH_WINDOW_DAYS)
    items = (
        (
            await db.execute(
                select(ContentItem)
                .where(
                    or_(ContentItem.published_at >= since, ContentItem.crawled_at >= since),
                )
                .order_by(ContentItem.crawled_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    counts: dict[str, int] = defaultdict(int)
    for start in range(0, len(items), 200):
        batch = list(items[start : start + 200])
        for data in (await refresh_items(db, batch, record=True)).values():
            counts[data["verdict"]] += 1
    await db.commit()
    return dict(counts)


async def verdicts_for(db: AsyncSession, items: list[ContentItem]) -> dict[int, dict[str, Any]]:
    """列表用：已有 verdict_data 的直接用，没有的现算；都叠加人工结论。"""
    marks = await _marks(db, [c.id for c in items])
    missing = [c for c in items if not c.verdict_data]
    fresh = await refresh_items(db, missing) if missing else {}
    out: dict[int, dict[str, Any]] = {}
    for c in items:
        out[c.id] = fresh.get(c.id) or _with_mark(dict(c.verdict_data or {}), marks.get(c.id))
    return out


async def mark_verdict(
    db: AsyncSession, content: ContentItem, user_verdict: str | None, note: str | None
) -> dict[str, Any]:
    """「不对」：改成正确的结论；传 None 撤销。"""
    existing = (await db.execute(select(VerdictMark).where(VerdictMark.content_id == content.id))).scalar_one_or_none()
    computed = (await refresh_items(db, [content]))[content.id]
    computed_verdict = computed.get("computed") or computed["verdict"]
    if user_verdict is None:
        if existing is not None:
            await db.delete(existing)
    elif existing is None:
        db.add(
            VerdictMark(content_id=content.id, computed_verdict=computed_verdict, user_verdict=user_verdict, note=note)
        )
    else:
        existing.user_verdict = user_verdict
        existing.computed_verdict = computed_verdict
        existing.note = note
    await db.flush()
    return (await refresh_items(db, [content]))[content.id]


async def agreement_rate(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """近 N 天：结论与你的标记、收藏、开项目的一致率（设置 · 评分说明）。"""
    since = datetime.now(UTC) - timedelta(days=days)
    marks = (await db.execute(select(VerdictMark).where(VerdictMark.updated_at >= since))).scalars().all()
    corrected = sum(1 for m in marks if m.user_verdict != m.computed_verdict)
    fav_rows = (
        await db.execute(
            select(ContentItem.verdict, func.count())
            .where(ContentItem.is_favorited.is_(True), ContentItem.crawled_at >= since)
            .group_by(ContentItem.verdict)
        )
    ).all()
    fav = {v or "none": n for v, n in fav_rows}
    fav_total = sum(fav.values())
    return {
        "days": days,
        "marks": len(marks),
        "corrected": corrected,
        "mark_agreement": None if not marks else round(1 - corrected / len(marks), 3),
        "favorites": fav_total,
        "favorites_worth": fav.get("worth", 0),
        "favorite_agreement": None if not fav_total else round(fav.get("worth", 0) / fav_total, 3),
    }
