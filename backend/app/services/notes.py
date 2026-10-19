"""随笔（改造方案 6.4）。

* 写一句就存：文字（Markdown）、图片、语音（录音存文件，转写成文字）、链接（自动收进灵感库并关联）。
* ``[[ ]]`` 关联收藏、专题、项目和其他随笔；``#标签``。
* 保存后给出相关的收藏和热点（本地向量；不可用时按关键词）。
* Obsidian：每天一个文件 ``随笔/YYYY-MM-DD.md``，每条随笔一个 ``## HH:MM ^cw-<id>`` 小节（见 obsidian_sync）。
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.dossier import TopicDossier
from app.models.library import LibraryItem, LibraryLink, LinkRelation, Note
from app.services import library_files
from app.services.library import add_file, add_from_link, ensure_link, json_has

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

TAG_RE = re.compile(r"(?<![\w#&])#([\w\u4e00-\u9fff][\w\u4e00-\u9fff/-]{0,30})")
WIKI_RE = re.compile(r"\[\[([^\[\]|]{1,160})(?:\|[^\]]*)?\]\]")
URL_RE = re.compile(r"https?://[^\s)>\]]+")


class NoteError(ValueError):
    pass


def parse_note(body: str) -> dict[str, list[str]]:
    """纯函数：标签、双链目标、链接。代码块里的不算。"""
    text = re.sub(r"```.*?```", "", body or "", flags=re.S)
    links = list(dict.fromkeys(m.strip() for m in WIKI_RE.findall(text)))
    # 双链里的 # 是标题锚点，不是标签；纯数字不算标签（与 Obsidian 一致）
    tag_text = re.sub(r"\[\[[^\]]*\]\]", "", text)
    tags = list(dict.fromkeys(t for t in TAG_RE.findall(tag_text) if not t.isdigit()))
    urls = list(dict.fromkeys(u.rstrip(".,，。") for u in URL_RE.findall(text)))
    return {"tags": tags, "wikilinks": links, "urls": urls}


async def resolve_wikilink(db: AsyncSession, target: str) -> tuple[str, int] | None:
    """[[标题]] → 灵感库条目 / 专题 / 随笔（按 ``随笔 #id``）/ 项目（阶段 4）。精确标题优先。"""
    t = target.strip()
    # 随笔块引用：Obsidian 里写 [[2026-10-18#^cw-123]]，或直接 [[cw-123]]
    m = re.search(r"(?:^|#\^)cw-(\d+)$", t)
    if m:
        n = await db.get(Note, int(m.group(1)))
        return ("note", n.id) if n else None
    t = t.split("#", 1)[0].strip()  # [[标题#小节]] 按标题解析
    if not t:
        return None
    item = (
        await db.execute(
            select(LibraryItem.id).where(LibraryItem.title == t, LibraryItem.archived_at.is_(None)).limit(1)
        )
    ).scalar()
    if item:
        return ("item", item)
    dossier = (await db.execute(select(TopicDossier.id).where(TopicDossier.title == t).limit(1))).scalar()
    if dossier:
        return ("dossier", dossier)
    from app.models.studio import StudioProject

    project = (await db.execute(select(StudioProject.id).where(StudioProject.title == t).limit(1))).scalar()
    if project:
        return ("project", project)
    item = (
        await db.execute(
            select(LibraryItem.id).where(LibraryItem.title.ilike(f"%{t}%"), LibraryItem.archived_at.is_(None)).limit(1)
        )
    ).scalar()
    return ("item", item) if item else None


async def _sync_links(db: AsyncSession, note: Note, parsed: dict[str, list[str]]) -> list[dict[str, Any]]:
    """重建这条随笔的双链（只动 wikilink 关系，手动关联保留）；链接收进灵感库并关联。"""
    old = (
        (
            await db.execute(
                select(LibraryLink).where(
                    LibraryLink.from_type == "note",
                    LibraryLink.from_id == note.id,
                    LibraryLink.relation == LinkRelation.WIKILINK.value,
                )
            )
        )
        .scalars()
        .all()
    )
    for link in old:
        await db.delete(link)
    await db.flush()
    resolved = []
    for target in parsed["wikilinks"]:
        ref = await resolve_wikilink(db, target)
        resolved.append({"text": target, "type": ref[0] if ref else None, "id": ref[1] if ref else None})
        if ref and ref != ("note", note.id):
            await ensure_link(db, ("note", note.id), ref, LinkRelation.WIKILINK.value)
    for url in parsed["urls"][:5]:
        try:
            item = await add_from_link(db, url)
            await ensure_link(db, ("note", note.id), ("item", item.id), LinkRelation.MANUAL.value)
        except Exception as exc:  # noqa: BLE001 — 链接收藏失败不影响随笔本身
            logger.info("note link import failed %s: %s", url, exc)
    return resolved


async def create_note(
    db: AsyncSession,
    body: str,
    *,
    source: str = "app",
    image_ids: list[int] | None = None,
    created_at: datetime | None = None,
) -> Note:
    body = (body or "").strip()
    if not body and not image_ids:
        raise NoteError("随笔是空的")
    parsed = parse_note(body)
    note = Note(body=body, tags=parsed["tags"] or None, source=source, image_item_ids=image_ids or None)
    if created_at:
        note.created_at = created_at
    db.add(note)
    await db.flush()
    await _sync_links(db, note, parsed)
    for iid in image_ids or []:
        await ensure_link(db, ("note", note.id), ("item", iid), LinkRelation.MANUAL.value)
    await db.commit()
    await db.refresh(note)
    return note


async def update_note(db: AsyncSession, note_id: int, body: str, *, from_obsidian: bool = False) -> Note:
    note = await db.get(Note, note_id)
    if note is None or note.deleted_at is not None:
        raise LookupError("随笔不存在")
    note.body = body.strip()
    parsed = parse_note(note.body)
    note.tags = parsed["tags"] or None
    if from_obsidian:
        note.obsidian_synced_at = datetime.now(UTC)
    await _sync_links(db, note, parsed)
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, note_id: int) -> None:
    note = await db.get(Note, note_id)
    if note is not None:
        note.deleted_at = datetime.now(UTC)
        await db.commit()


async def attach_audio(db: AsyncSession, note_id: int, content: bytes, filename: str) -> Note:
    note = await db.get(Note, note_id)
    if note is None:
        raise LookupError("随笔不存在")
    sf = library_files.store_bytes(content, filename or "voice.webm")
    note.audio_path = sf.path
    note.transcript_status = "pending"
    await db.commit()
    await db.refresh(note)
    return note


async def transcribe(db: AsyncSession, note_id: int) -> Note:
    """语音转写（千问）：用设置里的 OpenAI 兼容转写接口（DashScope 兼容模式），转写结果追加到正文，音频保留。"""
    from app.services.speech import SpeechNotConfigured, transcribe_file

    note = await db.get(Note, note_id)
    if note is None or not note.audio_path:
        raise LookupError("随笔没有录音")
    try:
        text = await transcribe_file(db, library_files.abs_path(note.audio_path))
    except SpeechNotConfigured as exc:
        note.transcript_status = "not_configured"
        await db.commit()
        raise NoteError(str(exc)) from exc
    except Exception:
        note.transcript_status = "failed"
        await db.commit()
        raise
    note.body = (note.body + "\n\n" if note.body else "") + text.strip()
    note.transcript_status = "done"
    parsed = parse_note(note.body)
    note.tags = parsed["tags"] or None
    await _sync_links(db, note, parsed)
    await db.commit()
    await db.refresh(note)
    return note


def note_view(n: Note, links: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": n.id,
        "body": n.body,
        "tags": n.tags or [],
        "audio": bool(n.audio_path),
        "transcript_status": n.transcript_status,
        "image_item_ids": n.image_item_ids or [],
        "source": n.source,
        "created_at": n.created_at,
        "updated_at": n.updated_at,
        "links": links or [],
    }


async def _links_for(db: AsyncSession, note_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    from app.services.library import resolve_refs

    if not note_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(LibraryLink).where(LibraryLink.from_type == "note", LibraryLink.from_id.in_(note_ids))
            )
        )
        .scalars()
        .all()
    )
    refs = [{"type": r.to_type, "id": r.to_id, "relation": r.relation, "note": r.from_id} for r in rows]
    resolved = await resolve_refs(db, refs)
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in resolved:
        out[r.pop("note")].append(r)
    return out


async def list_notes(
    db: AsyncSession,
    *,
    tag: str | None = None,
    linked: tuple[str, int] | None = None,
    q: str | None = None,
    before: date | None = None,
    days: int = 14,
) -> dict[str, Any]:
    """按日期排成时间线（像日记）。默认最近 14 天；``before`` 往前翻。"""
    stmt = select(Note).where(Note.deleted_at.is_(None))
    if tag:
        stmt = stmt.where(json_has(Note.tags, tag))
    if q:
        stmt = stmt.where(Note.body.ilike(f"%{q}%"))
    if linked:
        ids = select(LibraryLink.from_id).where(
            LibraryLink.from_type == "note", LibraryLink.to_type == linked[0], LibraryLink.to_id == linked[1]
        )
        stmt = stmt.where(Note.id.in_(ids))
    if not (tag or q or linked):
        end_day = before or datetime.now(LOCAL_TZ).date()
        end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=LOCAL_TZ)
        start = end - timedelta(days=days)
        stmt = stmt.where(Note.created_at >= start, Note.created_at < end)
    notes = (await db.execute(stmt.order_by(Note.created_at.desc()).limit(500))).scalars().all()
    links = await _links_for(db, [n.id for n in notes])
    days_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in notes:
        d = n.created_at.astimezone(LOCAL_TZ).date().isoformat()
        days_map[d].append(note_view(n, links.get(n.id)))
    tag_rows = (await db.execute(select(Note.tags).where(Note.tags.is_not(None), Note.deleted_at.is_(None)))).scalars()
    tag_counts: dict[str, int] = defaultdict(int)
    for tags in tag_rows:
        for t in tags or []:
            tag_counts[t] += 1
    return {
        "days": [{"date": d, "notes": days_map[d]} for d in sorted(days_map, reverse=True)],
        "tags": sorted(tag_counts.items(), key=lambda x: -x[1])[:40],
        "total": len(notes),
    }


async def related_for_note(db: AsyncSession, note: Note, *, limit: int = 6) -> dict[str, list[dict[str, Any]]]:
    """保存后显示相关的收藏和热点：本地向量可用时按相似度，否则按关键词。"""
    import asyncio

    from app.services import embeddings

    text = note.body or ""
    favorites: list[dict[str, Any]] = []
    hot: list[dict[str, Any]] = []
    if text and await asyncio.to_thread(embeddings.available):
        import numpy as np

        from app.models.content_observation import ContentEmbedding

        vec = (await asyncio.to_thread(embeddings.embed, [text[:500]]))[0]
        since = datetime.now(UTC) - timedelta(days=14)
        rows = (
            await db.execute(
                select(
                    ContentEmbedding.content_id, ContentEmbedding.vector, ContentItem.title, ContentItem.is_favorited
                )
                .join(ContentItem, ContentItem.id == ContentEmbedding.content_id)
                .where(or_(ContentItem.is_favorited.is_(True), ContentEmbedding.created_at >= since))
                .limit(3000)
            )
        ).all()
        if rows:
            mat = np.vstack([embeddings.from_bytes(v) for _, v, _, _ in rows])
            sims = mat @ vec
            order = np.argsort(-sims)
            for i in order[: limit * 4]:
                cid, _, title, fav = rows[int(i)]
                if sims[int(i)] < 0.55:
                    break
                entry = {"content_id": cid, "title": title, "similarity": round(float(sims[int(i)]), 3)}
                (favorites if fav else hot).append(entry)
    else:
        import jieba

        words = [w for w in jieba.cut_for_search(text) if len(w) >= 2][:6]
        if words:
            cond = or_(*[ContentItem.title.ilike(f"%{w}%") for w in words])
            for c in (
                await db.execute(
                    select(ContentItem).where(cond).order_by(ContentItem.crawled_at.desc()).limit(limit * 3)
                )
            ).scalars():
                entry = {"content_id": c.id, "title": c.title, "similarity": None}
                (favorites if c.is_favorited else hot).append(entry)
    return {"favorites": favorites[:limit], "hot": hot[:limit]}


async def note_days_between(db: AsyncSession, start: date, end: date) -> dict[str, list[Note]]:
    lo = datetime.combine(start, time.min, tzinfo=LOCAL_TZ)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=LOCAL_TZ)
    rows = (
        (
            await db.execute(
                select(Note)
                .where(Note.created_at >= lo, Note.created_at < hi, Note.deleted_at.is_(None))
                .order_by(Note.created_at)
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, list[Note]] = defaultdict(list)
    for n in rows:
        out[n.created_at.astimezone(LOCAL_TZ).date().isoformat()].append(n)
    return out


async def add_note_image(db: AsyncSession, content: bytes, filename: str, mime: str | None = None) -> LibraryItem:
    """随笔里粘贴的截图 / 图片：先进灵感库（剪贴板导入），再挂到随笔。"""
    return await add_file(db, content, filename, mime=mime, method="clipboard")


__all__ = [
    "NoteError",
    "create_note",
    "delete_note",
    "list_notes",
    "note_view",
    "parse_note",
    "related_for_note",
    "transcribe",
    "update_note",
]
