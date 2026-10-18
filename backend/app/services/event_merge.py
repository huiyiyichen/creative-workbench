"""事件归并（改造方案 4.1）：本地向量 + 时间窗，同一事件只完整分析一次。

流程（每 10 分钟，以及完整分析前）：

1. 给最近 72 小时还没有向量的内容算向量（bge-small-zh，CPU）。
2. 与窗口内其他内容比余弦相似度，超过阈值（默认 0.82，设置 ``event_merge_threshold``）的最相似一条
   所在事件就是它的事件；对方还没有事件时新建一个（写入现有 ``content_event_groups`` / ``members``）。
3. 选分析代表：已完整分析的优先，其次正文最全、信源价值高、发布最早。只有代表进入快速判断 / 完整分析；
   其他成员 ``full_eligible=False``，在 ``quick_result.event`` 里记录代表与事件，继承代表的分析结果。
4. 回填代表的初筛信号 ``coverage``（事件覆盖的平台数）并重算初筛分。

向量模型不可用时整步跳过，现有字面相似度的事件归一化任务不受影响。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.content_event import EventRelationType
from app.models.content_observation import ContentEmbedding
from app.repositories.app_setting_repo import AppSettingRepository
from app.repositories.event_merge_repo import EventMergeRepository
from app.services import embeddings
from app.services.content_event_service import ContentEventService, EventMemberInput
from app.services.content_journey import record_journey

logger = logging.getLogger(__name__)

WINDOW_HOURS = 72
DEFAULT_THRESHOLD = 0.82
DUPLICATE_THRESHOLD = 0.95
THRESHOLD_KEY = "event_merge_threshold"
DETECTOR = f"local-vector:{embeddings.MODEL_NAME}"


async def merge_threshold(db: AsyncSession) -> float:
    row = await AppSettingRepository(db).get_by_key(THRESHOLD_KEY)
    try:
        value = float(row.value) if row and row.value else DEFAULT_THRESHOLD
    except ValueError:
        value = DEFAULT_THRESHOLD
    return min(0.99, max(0.5, value))


def representative_key(item: ContentItem, source_value: dict[int, float] | None = None) -> tuple:
    """越小越优先：已完整分析 → 正文长度 → 信源价值 → 发布越早。"""
    published = item.published_at or item.crawled_at or datetime.max.replace(tzinfo=UTC)
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    text_len = len(item.raw_content or "") + len(item.summary or "")
    value = (source_value or {}).get(item.source_id or -1, 0.0)
    return (0 if item.analysis_level == "full" else 1, -min(text_len, 20000) // 500, -value, published, item.id)


def best_match(
    vec: np.ndarray, pool_ids: list[int], pool: np.ndarray, *, exclude: int, threshold: float
) -> tuple[int, float] | None:
    if pool.shape[0] == 0:
        return None
    sims = pool @ vec
    order = np.argsort(-sims)
    for idx in order[:5]:
        cid = pool_ids[int(idx)]
        if cid == exclude:
            continue
        score = float(sims[int(idx)])
        return (cid, score) if score >= threshold else None
    return None


def coverage_signal(platforms: set[str]) -> float:
    return round(min(1.0, max(0, len(platforms) - 1) / 3), 4)


async def _apply_representative(
    db: AsyncSession, group, members: list[ContentItem], *, source_value: dict[int, float]
) -> ContentItem:
    """确定代表，其余成员不再单独分析；代表的 coverage 信号回填。"""
    from app.services.triage import load_triage_context, rescore

    rep = min(members, key=lambda c: representative_key(c, source_value))
    current = next((c for c in members if c.id == group.representative_content_id), None)
    if current is not None and current.analysis_level == "full":
        rep = current  # 已经分析过的代表不换，避免重复花费
    group.representative_content_id = rep.id
    for item in members:
        if item.id == rep.id:
            if item.full_eligible is False and isinstance(item.quick_result, dict) and item.quick_result.get("event"):
                item.full_eligible = None  # 曾经是成员、现在成了代表：重新进入快速判断
                item.quick_result = None
            continue
        if item.analysis_level != "full":
            item.full_eligible = False
            item.quick_result = {**(item.quick_result or {}), "event": {"id": group.id, "representative": rep.id}}
    platforms = {c.platform or c.source_type or "web" for c in members}
    signals = dict(rep.triage_signals or {})
    signals["coverage"] = coverage_signal(platforms)
    signals["event_size"] = len(members)
    rep.triage_signals = signals
    ctx = await load_triage_context(db)
    rep.triage_score = rescore(signals, ctx.weights)
    return rep


async def merge_recent_events(db: AsyncSession, *, limit: int = 200) -> dict[str, Any]:
    if not await asyncio.to_thread(embeddings.available):
        return {"skipped": "embedding_unavailable", "reason": embeddings.unavailable_reason()}
    repo = EventMergeRepository(db)
    since = datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)
    new_items = list(await repo.contents_without_embedding(since=since, limit=limit))
    if not new_items:
        return {"embedded": 0, "merged": 0, "events_created": 0}

    texts = [embeddings.text_for(c.title, c.summary) for c in new_items]
    vectors = await asyncio.to_thread(embeddings.embed, texts)
    for item, vec in zip(new_items, vectors, strict=True):
        db.add(ContentEmbedding(content_id=item.id, model=embeddings.MODEL_NAME, vector=embeddings.to_bytes(vec)))
    await db.flush()

    # 初筛信号「与收藏的相似度」回填
    from app.services.triage import load_triage_context, rescore

    triage_ctx = await load_triage_context(db)
    for item, sim in zip(new_items, await favorite_similarity(db, vectors), strict=True):
        if sim is None or item.analysis_level == "full":
            continue
        signals = {**(item.triage_signals or {}), "similarity": sim}
        item.triage_signals = signals
        item.triage_score = rescore(signals, triage_ctx.weights)

    threshold = await merge_threshold(db)
    pool_rows = await repo.window_vectors(since=since)
    pool_ids = [cid for cid, _ in pool_rows]
    pool = (
        np.vstack([embeddings.from_bytes(v) for _, v in pool_rows])
        if pool_rows
        else np.zeros((0, embeddings.DIM), dtype=np.float32)
    )
    # 同一批里只和排在自己前面的比（批次按入库时间排序），保证先来的成为锚点
    batch_pos = {c.id: i for i, c in enumerate(new_items)}
    service = ContentEventService(db)
    source_value = triage_ctx.source_value
    merged = created = 0
    for item, vec in zip(new_items, vectors, strict=True):
        pos = batch_pos[item.id]
        keep = [i for i, cid in enumerate(pool_ids) if batch_pos.get(cid, -1) < pos]
        match = best_match(vec, [pool_ids[i] for i in keep], pool[keep], exclude=item.id, threshold=threshold)
        if match is None:
            continue
        other_id, score = match
        relation = EventRelationType.DUPLICATE if score >= DUPLICATE_THRESHOLD else EventRelationType.CORROBORATION
        try:
            async with db.begin_nested():
                if await repo.group_of(item.id) is not None:
                    continue
                group = await repo.group_of(other_id)
                if group is None:
                    other = (await repo.contents([other_id]))[0]
                    if other.owner_user_id != item.owner_user_id:
                        continue
                    group = await service.create_event(
                        [other_id, item.id],
                        owner_user_id=other.owner_user_id,
                        members={
                            other_id: EventMemberInput(other_id, relation, score, "local_vector", DETECTOR),
                            item.id: EventMemberInput(item.id, relation, score, "local_vector", DETECTOR),
                        },
                        classifier_version=DETECTOR,
                    )
                    created += 1
                else:
                    group = await service.add_member(
                        group.id,
                        item.id,
                        relation_type=relation,
                        confidence=score,
                        match_method="local_vector",
                        detector_version=DETECTOR,
                        reason=f"向量相似度 {score:.2f}",
                    )
                members = list(await repo.contents(await repo.group_content_ids(group)))
                rep = await _apply_representative(db, group, members, source_value=source_value)
        except Exception:
            logger.warning("event merge failed for content %s", item.id, exc_info=True)
            continue
        merged += 1
        await record_journey(
            db,
            item.id,
            "event",
            f"归入事件 #{group.id}（相似度 {score:.2f}，共 {len(members)} 条）"
            + ("，作为分析代表" if rep.id == item.id else "，继承代表的分析结果"),
            detail={"event_id": group.id, "representative": rep.id, "similarity": round(score, 4)},
        )
    await db.commit()
    return {"embedded": len(new_items), "merged": merged, "events_created": created}


async def favorite_similarity(db: AsyncSession, vectors: np.ndarray) -> list[float | None]:
    """初筛「与收藏的相似度」：与最相近的收藏的余弦相似度，映射到 0–1。没有收藏时返回 None。"""
    favs = await EventMergeRepository(db).favorite_vectors()
    if not favs or vectors.shape[0] == 0:
        return [None] * int(vectors.shape[0])
    mat = np.vstack([embeddings.from_bytes(v) for v in favs])
    best = (vectors @ mat.T).max(axis=1)
    # bge 的无关文本相似度约 0.3–0.5，相近主题 0.7 以上
    return [round(float(np.clip((b - 0.45) / 0.4, 0, 1)), 4) for b in best]
