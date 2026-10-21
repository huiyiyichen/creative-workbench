"""全局搜索：库内检索 + 按关键词去各平台现抓。

- ``search_all``：一次搜采集内容、灵感库、随笔、项目、产出、报告，按类型分组返回。
- ``crawl_keyword``：给关键词去平台搜索并入库。复用追踪词信源（kind=keyword）的整条采集链路，
  同一个词只建一个信源；``track=False`` 时只抓这一次（抓完把新建的信源停用，以后不自动跑）。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.library import LibraryItem, Note
from app.models.project import Project, ProjectOutput
from app.models.source import Source, SourceKind, SourceType

logger = logging.getLogger(__name__)

GROUPS = ("contents", "library", "notes", "projects", "outputs", "reports")
MAX_QUERY = 100


_TAIL = re.compile(r"(🔗\s*)?阅读原文.*$|\bvia\s+[A-Z][\w.]*\s*[•·]?\s*$")
_URL = re.compile(r"https?://\S+")


def clean_snippet_source(text: str) -> str:
    """摘要取材前去掉转载尾巴（「🔗 阅读原文 via AIHOT • https://…」）和裸 URL（评审 #4 P0-5）。"""
    flat = " ".join(_URL.sub(" ", text).split())
    flat = _TAIL.sub("", flat).strip(" •·-—")
    return flat


def snippet(text: str | None, q: str, width: int = 40) -> str | None:
    """取命中词前后各 width 字；没命中给开头一段。大小写不敏感。"""
    if not text:
        return None
    flat = clean_snippet_source(text)
    if not flat:
        return None
    i = flat.lower().find(q.lower())
    if i < 0:
        return flat[: width * 2] + ("…" if len(flat) > width * 2 else "")
    start = max(0, i - width)
    end = i + len(q) + width
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def _clean(q: str) -> str:
    q = " ".join((q or "").split())[:MAX_QUERY]
    if not q:
        raise ValueError("关键词不能为空")
    return q


def _needle(q: str) -> str:
    # ilike 通配符转义，免得「100%」这类词匹配到一切
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def search_all(
    db: AsyncSession, q: str, *, limit: int = 8, groups: tuple[str, ...] | None = None
) -> dict[str, Any]:
    q = _clean(q)
    needle = _needle(q)
    want = set(groups or GROUPS)
    out: dict[str, list[dict[str, Any]]] = {}

    if "contents" in want:
        rows = (
            await db.execute(
                select(ContentItem)
                .where(
                    or_(ContentItem.title.ilike(needle, escape="\\"), ContentItem.summary.ilike(needle, escape="\\"))
                )
                .order_by(func.coalesce(ContentItem.published_at, ContentItem.created_at).desc())
                .limit(limit)
            )
        ).scalars()
        out["contents"] = [
            {
                "id": c.id,
                "title": c.title,
                "snippet": snippet(c.summary, q) if c.summary and q.lower() not in c.title.lower() else None,
                "platform": c.platform,
                "at": c.published_at or c.created_at,
                "href": f"/items/{c.id}",
            }
            for c in rows
        ]

    if "library" in want:
        rows = (
            await db.execute(
                select(LibraryItem)
                .where(
                    LibraryItem.archived_at.is_(None),
                    or_(LibraryItem.title.ilike(needle, escape="\\"), LibraryItem.body.ilike(needle, escape="\\")),
                )
                .order_by(LibraryItem.created_at.desc())
                .limit(limit)
            )
        ).scalars()
        out["library"] = [
            {
                "id": it.id,
                "title": it.title,
                "snippet": snippet(it.body, q) if it.body else None,
                "kind": it.kind,
                "at": it.created_at,
                "href": f"/library?open={it.id}",
            }
            for it in rows
        ]

    if "notes" in want:
        rows = (
            await db.execute(
                select(Note)
                .where(Note.deleted_at.is_(None), Note.body.ilike(needle, escape="\\"))
                .order_by(Note.created_at.desc())
                .limit(limit)
            )
        ).scalars()
        out["notes"] = [
            {
                "id": n.id,
                "title": (n.body.strip().splitlines() or [""])[0][:60] or "随笔",
                "snippet": snippet(n.body, q),
                "at": n.created_at,
                "href": f"/notes?focus={n.id}",
            }
            for n in rows
        ]

    if "projects" in want:
        rows = (
            await db.execute(
                select(Project)
                .where(
                    Project.archived_at.is_(None),
                    or_(Project.title.ilike(needle, escape="\\"), cast(Project.spec, Text).ilike(needle, escape="\\")),
                )
                .order_by(Project.updated_at.desc())
                .limit(limit)
            )
        ).scalars()
        out["projects"] = [
            {
                "id": p.id,
                "title": p.title or (p.spec or {}).get("theme") or f"项目 {p.id}",
                "snippet": None if q.lower() in (p.title or "").lower() else snippet((p.spec or {}).get("theme"), q),
                "stage": p.stage,
                "at": p.updated_at,
                "href": f"/projects/{p.id}",
            }
            for p in rows
        ]

    if "outputs" in want:
        rows = (
            await db.execute(
                select(ProjectOutput)
                .where(
                    or_(
                        ProjectOutput.title.ilike(needle, escape="\\"),
                        cast(ProjectOutput.content, Text).ilike(needle, escape="\\"),
                    )
                )
                .order_by(ProjectOutput.created_at.desc())
                .limit(limit)
            )
        ).scalars()
        out["outputs"] = [
            {
                "id": o.id,
                "title": o.title or f"产出 {o.id}",
                "snippet": None,
                "kind": o.kind,
                "status": o.status,
                "at": o.created_at,
                "href": f"/projects/{o.project_id}/outputs/{o.id}",
            }
            for o in rows
        ]

    if "reports" in want:
        from app.services.period_reports import search_reports

        out["reports"] = [
            {**r, "title": r["label"], "href": _report_href(r)} for r in await search_reports(db, q, limit=limit)
        ]

    return {"q": q, "groups": out, "total": sum(len(v) for v in out.values())}


def _report_href(r: dict[str, Any]) -> str:
    kind = r.get("kind")
    if kind == "daily":
        return f"/daily?date={r['key']}"
    if kind == "weekly":
        return "/weekly"
    if kind == "monthly":
        return "/monthly"
    return f"/reports/periods/{r['id']}"


# ── 按关键词去平台抓 ──────────────────────────────────────────────


async def find_keyword_source(db: AsyncSession, q: str) -> Source | None:
    return (
        (
            await db.execute(
                select(Source)
                .where(Source.kind == SourceKind.KEYWORD.value, func.lower(Source.query) == q.lower())
                .order_by(Source.id)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def crawl_keyword(
    db: AsyncSession, q: str, *, platforms: list[str] | None = None, track: bool = False
) -> dict[str, Any]:
    """抓一次关键词。返回同步结果与这次信源下最新的条目。"""
    from app.core.config import settings
    from app.models.source_sync_run import SyncTrigger
    from app.services.collection_service import list_source_recent
    from app.services.content_pipeline import ingest_from_source
    from app.services.source_registry import create_source, searchable_platforms
    from app.services.source_sync_service import run_source_sync

    q = _clean(q)
    allowed = searchable_platforms()
    chosen = [p for p in (platforms or allowed) if p in allowed]
    if not chosen:
        raise ValueError("没有可搜索的平台")

    source = await find_keyword_source(db, q)
    created = source is None
    if source is None:
        source = await create_source(
            db,
            {
                "kind": SourceKind.KEYWORD.value,
                "source_type": SourceType.KEYWORD.value,
                "url": f"keyword://{quote(q, safe='')}",
                "name": q,
                "query": q,
                "platforms": chosen,
            },
        )
    else:
        source.platforms = chosen
    was_enabled = bool(source.enabled)
    # 已停用的追踪词也允许手动抓一次：临时打开，抓完按 track 决定
    source.enabled = True
    await db.commit()
    source_id = source.id

    outcome = await run_source_sync(
        db,
        source_id,
        trigger=SyncTrigger.MANUAL,
        lease_seconds=int(settings.SOURCE_SYNC_TIMEOUT_SECONDS),
        ingest=ingest_from_source,
    )
    fresh = await db.get(Source, source_id)
    if fresh is not None:
        fresh.enabled = True if track else (was_enabled and not created)
        await db.commit()

    run = outcome.run
    if run is None:
        status = "busy" if outcome.skipped_reason == "lease_active" else (outcome.skipped_reason or "skipped")
        result = {"status": status, "fetched": 0, "new": 0, "duplicates": 0, "error_message": None}
    else:
        if not outcome.failed:
            from app._post_sync_pipeline import _request_post_sync_pipeline

            _request_post_sync_pipeline(outcome.stats)
        result = {
            "status": run.status,
            "fetched": run.fetched,
            "new": run.new,
            "duplicates": run.duplicates,
            "error_message": run.error_message,
        }
    return {
        **result,
        "q": q,
        "source_id": source_id,
        "created": created,
        "tracking": bool(fresh.enabled) if fresh is not None else False,
        "platforms": chosen,
        "items": await list_source_recent(db, source_id, limit=30),
    }
