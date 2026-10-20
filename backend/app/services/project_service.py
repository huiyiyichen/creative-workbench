"""阶段 4 创作工作台：项目、来源快照、文稿工作副本、版本、定稿 / 解锁、产出物、素材。

约定（设计文档 3–6、10–11 节）：
- ``studio_projects.spec`` 是工作副本：``brief``（只含文案层）、``draft``、``template``、``idea``。
- 自动保存只写工作副本并换 ``draft_token``，不生成版本；只有保存版本、AI 成稿、接受 AI 建议、定稿生成版本。
- 制作层参数（风格、表现方案、画幅、配音、字幕卡）放在产出物 ``settings``，修改不撤销定稿。
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundError, ValidationError
from app.models.content import ContentItem
from app.models.library import LibraryItem
from app.models.metrics import ContentMetrics
from app.models.project import (
    Project,
    ProjectArtifact,
    ProjectAsset,
    ProjectOutput,
    ProjectRevision,
    ProjectSource,
)
from app.schemas.projects import (
    COPY_FIELDS,
    PRODUCTION_FIELDS,
    AssetAdd,
    BriefSave,
    CopyBrief,
    DraftSave,
    OutputCreate,
    OutputPatch,
    ProjectCreate,
    SourceAdd,
)
from app.schemas.studio import StudioBrief, StudioDraft

logger = logging.getLogger(__name__)

MAX_REFERENCES = 9
MAX_MOODBOARD = 30
OUTPUT_TITLES = {
    "xhs": "小红书版",
    "zhihu": "知乎版",
    "wechat": "公众号版",
    "video": "讲解视频",
    "mv": "音乐 MV",
    "prompt_bundle": "视频提示词包",
}
RENDER_KINDS = {"video", "mv", "prompt_bundle"}  # 定稿后才能「开始」


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _token() -> str:
    return uuid.uuid4().hex


def conflict(code: str, message: str, **details: Any) -> AppException:
    return AppException(message, 409, {"code": code, **details})


# ── 段落稳定 id ──────────────────────────────────────────────────────

_PARA_SPLIT = re.compile(r"\n\s*\n")


def split_paragraphs(body: str) -> list[str]:
    return [p.strip("\n") for p in _PARA_SPLIT.split(body or "") if p.strip()]


def paragraph_ids(paragraphs: list[str]) -> list[str]:
    """``p_`` + 内容哈希前 8 位；同文重复时追加序号。"""
    seen: dict[str, int] = {}
    ids: list[str] = []
    for text in paragraphs:
        base = "p_" + hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:8]
        n = seen.get(base, 0)
        seen[base] = n + 1
        ids.append(base if n == 0 else f"{base}_{n + 1}")
    return ids


def paragraphs_with_ids(body: str) -> list[dict]:
    paras = split_paragraphs(body)
    return [{"id": pid, "text": text} for pid, text in zip(paragraph_ids(paras), paras, strict=True)]


# ── 文案层 / 制作层 ──────────────────────────────────────────────────


def copy_brief(raw: dict | None) -> dict:
    raw = raw or {}
    return CopyBrief.model_validate({k: raw[k] for k in COPY_FIELDS if k in raw and raw[k] is not None}).model_dump(
        mode="json"
    )


def production_settings(raw: dict | None) -> dict:
    raw = raw or {}
    return {k: raw[k] for k in PRODUCTION_FIELDS if raw.get(k) is not None}


def studio_brief(brief: dict, settings: dict | None = None) -> StudioBrief:
    """文案层 + 制作层合成旧的 StudioBrief，供 compile_draft / 制作链路复用。"""
    merged = {**copy_brief(brief), **production_settings(settings)}
    merged.pop("tone", None)
    merged["theme"] = merged.get("theme") or "未命名选题"
    return StudioBrief.model_validate(merged)


def _draft_payload(draft: dict | None) -> dict:
    return StudioDraft.model_validate(draft or {}).model_dump(mode="json", exclude={"provenance"})


def copy_layer_changed(old_brief: dict, new_brief: dict, old_draft: dict | None, new_draft: dict | None) -> bool:
    if copy_brief(old_brief) != copy_brief(new_brief):
        return True
    if old_draft is None and new_draft is None:
        return False
    return _draft_payload(old_draft) != _draft_payload(new_draft)


# ── 读取 ─────────────────────────────────────────────────────────────


async def get_project(db: AsyncSession, project_id: int, *, lock: bool = False) -> Project:
    stmt = select(Project).where(Project.id == project_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise NotFoundError("项目", project_id)
    return project


async def _latest_revision(db: AsyncSession, project_id: int) -> ProjectRevision | None:
    stmt = (
        select(ProjectRevision)
        .where(ProjectRevision.project_id == project_id)
        .order_by(ProjectRevision.version.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _is_dirty(db: AsyncSession, project: Project) -> bool:
    latest = await _latest_revision(db, project.id)
    spec = project.spec or {}
    if latest is None:
        draft = StudioDraft.model_validate(spec.get("draft") or {})
        return bool(draft.body.strip() or draft.shots)
    return copy_layer_changed(
        latest.spec.get("brief", {}), spec.get("brief", {}), latest.spec.get("draft"), spec.get("draft")
    )


def _status(project: Project, dirty: bool) -> str:
    if project.finalized_version and not dirty:
        return "finalized"
    return "dirty" if dirty else "draft"


def project_summary(project: Project, *, dirty: bool = False, counts: dict | None = None) -> dict:
    spec = project.spec or {}
    brief = copy_brief(spec.get("brief"))
    return {
        "id": project.id,
        "title": project.title,
        "theme": brief.get("theme"),
        "mode": brief.get("mode"),
        "stage": project.stage or "idea",
        "version": project.version,
        "finalized_version": project.finalized_version,
        "status": _status(project, dirty),
        "dirty": dirty,
        "archived": project.archived_at is not None,
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
        **(counts or {}),
    }


async def list_projects(db: AsyncSession, *, stage: str | None = None, q: str | None = None, archived: bool = False):
    stmt = select(Project)
    stmt = stmt.where(Project.archived_at.is_not(None) if archived else Project.archived_at.is_(None))
    if stage:
        stmt = stmt.where(Project.stage == stage)
    if q:
        stmt = stmt.where(Project.title.ilike(f"%{q.strip()}%"))
    projects = (await db.execute(stmt.order_by(Project.updated_at.desc()).limit(200))).scalars().all()
    ids = [p.id for p in projects]
    out_counts: dict[int, int] = {}
    main_titles: dict[int, dict] = {}
    if ids:
        rows = await db.execute(
            select(ProjectOutput.project_id, func.count())
            .where(ProjectOutput.project_id.in_(ids))
            .group_by(ProjectOutput.project_id)
        )
        out_counts = dict(rows.all())
        for src in (
            await db.execute(
                select(ProjectSource).where(ProjectSource.project_id.in_(ids), ProjectSource.role == "main")
            )
        ).scalars():
            main_titles[src.project_id] = {
                "title": src.snapshot.get("title"),
                "cover_url": src.snapshot.get("cover_url"),
                "platform": src.snapshot.get("platform"),
            }
    return {
        "items": [
            project_summary(p, counts={"outputs": out_counts.get(p.id, 0), "main_source": main_titles.get(p.id)})
            for p in projects
        ]
    }


async def project_view(db: AsyncSession, project_id: int) -> dict:
    project = await get_project(db, project_id)
    dirty = await _is_dirty(db, project)
    sources = await list_sources(db, project_id)
    running = (
        await db.execute(
            select(func.count())
            .select_from(ProjectArtifact)
            .where(ProjectArtifact.project_id == project_id, ProjectArtifact.status.in_(["queued", "rendering"]))
        )
    ).scalar_one()
    spec = project.spec or {}
    return {
        **project_summary(project, dirty=dirty),
        "brief": copy_brief(spec.get("brief")),
        "idea": spec.get("idea") or {},
        "ai_draft": spec.get("ai_draft") or {},
        "platform_rewrite": spec.get("platform_rewrite") or {},
        "pipeline": _pipeline_view(spec),
        "sources": sources,
        "running_tasks": running,
        "draft_token": project.draft_token,
    }


# ── 项目 ─────────────────────────────────────────────────────────────


def _parse_source_ref(ref: str) -> tuple[str, int]:
    kind, _, raw = ref.partition(":")
    if kind not in {"content", "library", "note"} or not raw.isdigit():
        raise ValidationError(f"来源格式不对：{ref}（应为 content:123、library:45 或 note:7）")
    return kind, int(raw)


async def create_project(db: AsyncSession, owner_id: int, request: ProjectCreate) -> dict:
    brief = copy_brief({"theme": request.theme, "mode": request.mode})
    spec = {"brief": brief, "draft": StudioDraft(title=request.theme).model_dump(mode="json"), "idea": {}}
    project = Project(
        owner_id=owner_id,
        title=(request.theme or "未命名项目")[:120],
        spec=spec,
        source_snapshot={},
        version=0,
        draft_token=_token(),
        stage="idea",
    )
    db.add(project)
    await db.flush()
    # 随笔不是来源：正文写进创作思路（「用于新项目」）
    refs = [_parse_source_ref(r) for r in request.sources]
    note_ids = [rid for kind, rid in refs if kind == "note"]
    if note_ids:
        from app.models.library import Note

        notes = (await db.execute(select(Note).where(Note.id.in_(note_ids)))).scalars().all()
        bodies = [n.body.strip() for n in notes if (n.body or "").strip()]
        if bodies:
            spec = deepcopy(project.spec)
            spec["brief"]["intent"] = "\n\n".join(bodies)[:5000]
            if not request.theme:
                first = bodies[0].splitlines()[0].strip("# ").strip()
                spec["brief"]["theme"] = first[:120]
                project.title = first[:120] or project.title
            project.spec = spec
    for index, (kind, rid) in enumerate((k, r) for k, r in refs if k != "note"):
        await add_source(
            db,
            project.id,
            SourceAdd(
                content_id=rid if kind == "content" else None,
                library_item_id=rid if kind == "library" else None,
                role="main" if index == 0 else "reference",
            ),
            commit=False,
        )
    if not request.theme:
        main = (
            await db.execute(
                select(ProjectSource).where(ProjectSource.project_id == project.id, ProjectSource.role == "main")
            )
        ).scalar_one_or_none()
        if main and main.snapshot.get("title"):
            project.title = main.snapshot["title"][:120]
    await db.commit()
    for kind, rid in refs:
        if kind == "content":
            _comments_later(rid)
    from app.services import feishu_service

    try:  # 可选：新建项目时自动记入飞书
        await feishu_service.on_project_created(db, project.id)
    except Exception:  # noqa: BLE001
        logger.warning("feishu create hook failed", exc_info=True)
    return await project_view(db, project.id)


async def _feishu_stage(db: AsyncSession, project_id: int) -> None:
    """项目阶段变化：已记入飞书的项目后台更新状态列（失败不影响主流程）。"""
    from app.services import feishu_service

    try:
        await feishu_service.on_project_stage(db, project_id)
    except Exception:  # noqa: BLE001
        logger.warning("feishu stage hook failed", exc_info=True)


def _comments_later(content_id: int) -> None:
    """被项目用作来源：后台采一次评论（3.5 触发条件 2）。"""
    from app.services import comments

    comments.collect_in_background(content_id)


async def rename_project(db: AsyncSession, project_id: int, title: str) -> dict:
    project = await get_project(db, project_id)
    project.title = title.strip()[:120]
    await db.commit()
    return await project_view(db, project_id)


async def archive_project(db: AsyncSession, project_id: int, archived: bool = True) -> dict:
    project = await get_project(db, project_id)
    project.archived_at = _now() if archived else None
    await db.commit()
    return project_summary(project)


# ── 来源 ─────────────────────────────────────────────────────────────


async def _content_snapshot(db: AsyncSession, content_id: int) -> dict:
    content = await db.get(ContentItem, content_id)
    if not content:
        raise NotFoundError("内容", content_id)
    metric = (
        await db.execute(
            select(ContentMetrics)
            .where(ContentMetrics.content_id == content_id)
            .order_by(ContentMetrics.snapshot_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    metrics = {}
    if metric:
        metrics = {
            k: getattr(metric, k)
            for k in ("views", "likes", "comments", "shares", "favorites")
            if getattr(metric, k) is not None
        }
        metrics["observed_at"] = _iso(metric.snapshot_at)
    return {
        "kind": "content",
        "title": content.title,
        "url": content.url,
        "platform": content.platform or content.source_name,
        "author": content.author,
        "published_at": _iso(content.published_at),
        "crawled_at": _iso(content.crawled_at),
        "summary": (content.summary or "")[:2000],
        "cover_url": content.cover_url,
        "media_type": content.media_type,
        "metrics": metrics,
    }


async def _library_snapshot(db: AsyncSession, item_id: int) -> dict:
    item = await db.get(LibraryItem, item_id)
    if not item:
        raise NotFoundError("灵感库条目", item_id)
    return {
        "kind": "library",
        "title": item.title,
        "url": item.url or item.source_url,
        "platform": item.platform,
        "author": item.author,
        "published_at": None,
        "crawled_at": _iso(item.created_at),
        "summary": (item.ai_description or item.body or "")[:2000],
        "cover_url": item.cover_url,
        "content_id": item.content_id,
        "asset_kind": item.asset_kind or item.kind,
        "metrics": {},
    }


def source_dict(src: ProjectSource) -> dict:
    return {
        "id": src.id,
        "role": src.role,
        "content_id": src.content_id,
        "library_item_id": src.library_item_id,
        "ref": f"content:{src.content_id}" if src.content_id else f"library:{src.library_item_id}",
        "snapshot": src.snapshot,
        "added_at": _iso(src.added_at),
    }


async def _sources(db: AsyncSession, project_id: int) -> list[ProjectSource]:
    stmt = select(ProjectSource).where(ProjectSource.project_id == project_id).order_by(ProjectSource.id)
    return list((await db.execute(stmt)).scalars().all())


async def list_sources(db: AsyncSession, project_id: int) -> list[dict]:
    rows = await _sources(db, project_id)
    rows.sort(key=lambda s: (s.role != "main", s.id))
    return [source_dict(s) for s in rows]


async def add_source(db: AsyncSession, project_id: int, request: SourceAdd, *, commit: bool = True) -> dict:
    await get_project(db, project_id)
    existing = await _sources(db, project_id)
    for src in existing:
        if (request.content_id and src.content_id == request.content_id) or (
            request.library_item_id and src.library_item_id == request.library_item_id
        ):
            if request.role != src.role:
                return await set_source_role(db, project_id, src.id, request.role, commit=commit)
            return source_dict(src)
    refs = [s for s in existing if s.role == "reference"]
    if request.role == "reference" and len(refs) >= MAX_REFERENCES:
        raise ValidationError(f"参考最多 {MAX_REFERENCES} 条")
    snapshot = (
        await _content_snapshot(db, request.content_id)
        if request.content_id
        else await _library_snapshot(db, request.library_item_id)  # type: ignore[arg-type]
    )
    if request.role == "main":
        for src in existing:
            if src.role == "main":
                if len(refs) >= MAX_REFERENCES:
                    raise ValidationError("参考已满，无法把原主来源降为参考")
                src.role = "reference"
    src = ProjectSource(
        project_id=project_id,
        content_id=request.content_id,
        library_item_id=request.library_item_id,
        role=request.role,
        snapshot=snapshot,
    )
    db.add(src)
    await db.flush()
    if commit:
        await db.commit()
        if src.content_id:
            _comments_later(src.content_id)
    return source_dict(src)


async def set_source_role(db: AsyncSession, project_id: int, source_id: int, role: str, *, commit: bool = True) -> dict:
    rows = await _sources(db, project_id)
    target = next((s for s in rows if s.id == source_id), None)
    if not target:
        raise NotFoundError("项目来源", source_id)
    if role == "main":
        for s in rows:
            if s.role == "main" and s.id != source_id:
                s.role = "reference"
    elif target.role != "reference" and sum(1 for s in rows if s.role == "reference") >= MAX_REFERENCES:
        raise ValidationError(f"参考最多 {MAX_REFERENCES} 条")
    target.role = role
    await db.flush()
    if commit:
        await db.commit()
    return source_dict(target)


async def remove_source(db: AsyncSession, project_id: int, source_id: int) -> None:
    rows = await _sources(db, project_id)
    target = next((s for s in rows if s.id == source_id), None)
    if not target:
        raise NotFoundError("项目来源", source_id)
    await db.delete(target)
    await db.commit()


# ── 文案层设定 / 工作副本 ────────────────────────────────────────────


def _check_token(project: Project, token: str | None) -> None:
    if token is not None and project.draft_token and token != project.draft_token:
        raise conflict("draft_conflict", "这份文稿在另一个窗口改过", draft_token=project.draft_token)


async def save_brief(db: AsyncSession, project_id: int, request: BriefSave) -> dict:
    project = await get_project(db, project_id, lock=True)
    _check_token(project, request.draft_token)
    spec = deepcopy(project.spec or {})
    new_brief = request.brief.model_dump(mode="json")
    if project.finalized_version and copy_brief(spec.get("brief")) != copy_brief(new_brief):
        raise conflict("finalized", "已定稿，修改设定前需要先「继续修改」解锁")
    spec["brief"] = new_brief
    if request.idea is not None:
        spec["idea"] = request.idea
    if new_brief.get("theme") and (not project.title or project.title == "未命名项目"):
        project.title = new_brief["theme"][:120]
    project.spec = spec
    project.draft_token = _token()
    await db.commit()
    return await project_view(db, project_id)


async def draft_view(db: AsyncSession, project_id: int) -> dict:
    project = await get_project(db, project_id)
    spec = project.spec or {}
    draft = StudioDraft.model_validate(spec.get("draft") or {}).model_dump(mode="json")
    return {
        "brief": copy_brief(spec.get("brief")),
        "draft": draft,
        "paragraphs": paragraphs_with_ids(draft.get("body", "")),
        "template": spec.get("template"),
        "draft_token": project.draft_token,
        "version": project.version,
        "finalized_version": project.finalized_version,
        "dirty": await _is_dirty(db, project),
        "updated_at": _iso(project.updated_at),
    }


async def _snapshot(db: AsyncSession, project: Project, reason: str) -> int:
    project.version = (project.version or 0) + 1
    db.add(ProjectRevision(project_id=project.id, version=project.version, spec=deepcopy(project.spec), reason=reason))
    await db.flush()
    return project.version


async def save_draft(db: AsyncSession, project_id: int, request: DraftSave) -> dict:
    """自动保存：只写工作副本、换 token，不生成版本。"""
    project = await get_project(db, project_id, lock=True)
    if project.finalized_version:
        raise conflict("finalized", "已定稿，点「继续修改」后才能编辑")
    if request.draft_token is not None and project.draft_token and request.draft_token != project.draft_token:
        if not request.force:
            raise conflict("draft_conflict", "这份文稿在另一个窗口改过", draft_token=project.draft_token)
        await _snapshot(db, project, "overwritten")  # 覆盖前先把对方的内容存成一个版本
    spec = deepcopy(project.spec or {})
    spec["draft"] = request.draft.model_dump(mode="json")
    project.spec = spec
    project.draft_token = _token()
    if project.stage == "idea":
        project.stage = "draft"
    await db.commit()
    return {"draft_token": project.draft_token, "version": project.version, "saved_at": _iso(_now())}


async def create_version(db: AsyncSession, project_id: int, reason: str = "manual") -> dict:
    project = await get_project(db, project_id, lock=True)
    version = await _snapshot(db, project, reason)
    await db.commit()
    return {"version": version, "draft_token": project.draft_token}


async def write_draft_version(db: AsyncSession, project_id: int, draft: StudioDraft, reason: str) -> dict:
    """AI 成稿、接受建议等：写工作副本并生成版本。"""
    project = await get_project(db, project_id, lock=True)
    spec = deepcopy(project.spec or {})
    spec["draft"] = draft.model_dump(mode="json")
    project.spec = spec
    project.draft_token = _token()
    project.finalized_version = None
    if project.stage == "idea":
        project.stage = "draft"
    version = await _snapshot(db, project, reason)
    await db.commit()
    return {"version": version, "draft_token": project.draft_token}


async def list_versions(db: AsyncSession, project_id: int) -> dict:
    project = await get_project(db, project_id)
    rows = (
        await db.execute(
            select(ProjectRevision)
            .where(ProjectRevision.project_id == project_id)
            .order_by(ProjectRevision.version.desc())
        )
    ).scalars()
    return {
        "finalized_version": project.finalized_version,
        "items": [
            {
                "version": r.version,
                "reason": r.reason,
                "created_at": _iso(r.created_at),
                "finalized": r.version == project.finalized_version,
            }
            for r in rows
        ],
    }


async def _revision(db: AsyncSession, project_id: int, version: int) -> ProjectRevision:
    rev = (
        await db.execute(
            select(ProjectRevision).where(ProjectRevision.project_id == project_id, ProjectRevision.version == version)
        )
    ).scalar_one_or_none()
    if not rev:
        raise NotFoundError("版本", version)
    return rev


async def version_view(db: AsyncSession, project_id: int, version: int) -> dict:
    rev = await _revision(db, project_id, version)
    draft = StudioDraft.model_validate(rev.spec.get("draft") or {}).model_dump(mode="json")
    return {
        "version": rev.version,
        "reason": rev.reason,
        "created_at": _iso(rev.created_at),
        "brief": copy_brief(rev.spec.get("brief")),
        "draft": draft,
        "paragraphs": paragraphs_with_ids(draft.get("body", "")),
    }


async def restore_version(db: AsyncSession, project_id: int, version: int) -> dict:
    project = await get_project(db, project_id, lock=True)
    if project.finalized_version:
        raise conflict("finalized", "已定稿，先「继续修改」再恢复版本")
    rev = await _revision(db, project_id, version)
    spec = deepcopy(project.spec or {})
    spec["brief"] = deepcopy(rev.spec.get("brief", spec.get("brief")))
    spec["draft"] = deepcopy(rev.spec.get("draft", spec.get("draft")))
    project.spec = spec
    project.draft_token = _token()
    new_version = await _snapshot(db, project, f"restored:v{version}")
    await db.commit()
    return {"version": new_version, "draft_token": project.draft_token}


async def finalize(db: AsyncSession, project_id: int, version: int | None = None) -> dict:
    project = await get_project(db, project_id, lock=True)
    dirty = await _is_dirty(db, project)
    if version is not None and (version != project.version or dirty):
        raise conflict("stale_version", "只能定稿当前最新内容", current_version=project.version)
    draft = StudioDraft.model_validate((project.spec or {}).get("draft") or {})
    if not (draft.body.strip() or draft.shots):
        raise ValidationError("文稿还是空的，写点内容再定稿")
    if dirty or not project.version:
        await _snapshot(db, project, "finalized")
    project.finalized_version = project.version
    project.stage = "outputs"
    await db.commit()
    from app.services import pipeline_service

    try:  # 全流程在等定稿时，定稿后自动开始制作与平台改写
        await pipeline_service.on_finalized(db, project_id)
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.warning("pipeline after finalize failed", exc_info=True)
    await _feishu_stage(db, project_id)
    return await project_view(db, project_id)


async def unlock(db: AsyncSession, project_id: int) -> dict:
    project = await get_project(db, project_id, lock=True)
    project.finalized_version = None
    project.draft_token = _token()
    await db.commit()
    return await project_view(db, project_id)


async def finalized_spec(db: AsyncSession, project: Project) -> dict:
    if not project.finalized_version:
        raise conflict("not_finalized", "定稿后可制作")
    return deepcopy((await _revision(db, project.id, project.finalized_version)).spec)


# ── 产出物 ───────────────────────────────────────────────────────────


def output_dict(output: ProjectOutput, project: Project | None = None, artifacts: list | None = None) -> dict:
    stale = bool(
        project
        and project.finalized_version
        and output.based_on_version
        and project.finalized_version > output.based_on_version
    )
    data = {
        "id": output.id,
        "project_id": output.project_id,
        "kind": output.kind,
        "title": output.title or OUTPUT_TITLES.get(output.kind, output.kind),
        "status": output.status,
        "based_on_version": output.based_on_version,
        "latest_finalized": project.finalized_version if project else None,
        "stale": stale,
        "content": output.content or {},
        "settings": output.settings or {},
        "published_url": output.published_url,
        "published_at": _iso(output.published_at),
        "created_at": _iso(output.created_at),
        "updated_at": _iso(output.updated_at),
        "can_start": bool(project and project.finalized_version) or output.kind not in RENDER_KINDS,
    }
    if artifacts is not None:
        data["artifacts"] = artifacts
    return data


async def list_outputs(db: AsyncSession, project_id: int) -> dict:
    project = await get_project(db, project_id)
    rows = (
        await db.execute(select(ProjectOutput).where(ProjectOutput.project_id == project_id).order_by(ProjectOutput.id))
    ).scalars()
    return {"finalized_version": project.finalized_version, "items": [output_dict(o, project) for o in rows]}


async def get_output(db: AsyncSession, output_id: int) -> ProjectOutput:
    output = await db.get(ProjectOutput, output_id)
    if not output:
        raise NotFoundError("产出物", output_id)
    return output


def _default_settings(kind: str, brief: dict) -> dict:
    if kind in {"video", "mv"}:
        return {
            "presentation": "kinetic" if kind == "video" else None,
            "production": "code_animation" if kind == "video" else "native_mv",
            "aspect_ratio": "16:9",
            "bilingual": False,
            "style_id": None,
            "executor": "deepseek_harness",
        }
    if kind == "prompt_bundle":
        return {"target": "generic", "include": ["script", "storyboard", "style", "assets", "delivery"]}
    return {}


async def create_output(db: AsyncSession, project_id: int, request: OutputCreate) -> dict:
    project = await get_project(db, project_id)
    if request.kind in RENDER_KINDS and not project.finalized_version:
        raise conflict("not_finalized", "定稿后可制作")
    output = ProjectOutput(
        project_id=project_id,
        kind=request.kind,
        title=request.title or OUTPUT_TITLES[request.kind],
        status="draft",
        based_on_version=project.finalized_version,
        content={},
        settings=_default_settings(request.kind, (project.spec or {}).get("brief", {})),
    )
    db.add(output)
    await db.commit()
    return output_dict(output, project)


async def output_view(db: AsyncSession, output_id: int) -> dict:
    from app.services.studio_service import artifact_dict

    output = await get_output(db, output_id)
    project = await get_project(db, output.project_id)
    arts = (
        await db.execute(
            select(ProjectArtifact).where(ProjectArtifact.output_id == output_id).order_by(ProjectArtifact.id.desc())
        )
    ).scalars()
    return output_dict(output, project, [{**artifact_dict(a), "settings": a.settings} for a in arts])


async def patch_output(db: AsyncSession, output_id: int, request: OutputPatch) -> dict:
    """改平台文本或制作层参数：不触碰项目的定稿状态。"""
    output = await get_output(db, output_id)
    if request.title is not None:
        output.title = request.title
    if request.content is not None:
        output.content = request.content
    if request.settings is not None:
        output.settings = {**(output.settings or {}), **request.settings}
    if request.published_url is not None:
        url = request.published_url.strip()
        if url and not url.startswith(("http://", "https://")):
            raise ValidationError("发布链接需以 http(s):// 开头")
        output.published_url = url or None
        output.published_at = _now() if url else None
        output.status = "published" if url else "draft"
    elif request.status is not None:
        output.status = request.status
    await db.commit()
    if request.published_url is not None or request.status is not None:
        await _feishu_stage(db, output.project_id)
    return await output_view(db, output_id)


async def delete_output(db: AsyncSession, output_id: int) -> None:
    output = await get_output(db, output_id)
    await db.delete(output)
    await db.commit()


# ── 素材（情绪板等）─────────────────────────────────────────────────


def _asset_dict(asset: ProjectAsset, item: LibraryItem | None) -> dict:
    return {
        "id": asset.id,
        "role": asset.role,
        "target": asset.target,
        "library_item_id": asset.library_item_id,
        "added_at": _iso(asset.added_at),
        "item": (
            {
                "id": item.id,
                "kind": item.kind,
                "asset_kind": item.asset_kind,
                "title": item.title,
                "thumb": bool(item.thumb_small),
                "color": item.dominant_color,
                "license": item.license,
                "body": (item.body or "")[:200] if item.kind in {"note", "prompt"} else None,
            }
            if item
            else None
        ),
    }


async def list_assets(db: AsyncSession, project_id: int, role: str | None = None) -> dict:
    await get_project(db, project_id)
    stmt = select(ProjectAsset, LibraryItem).outerjoin(LibraryItem, LibraryItem.id == ProjectAsset.library_item_id)
    stmt = stmt.where(ProjectAsset.project_id == project_id)
    if role:
        stmt = stmt.where(ProjectAsset.role == role)
    rows = (await db.execute(stmt.order_by(ProjectAsset.id))).all()
    return {"items": [_asset_dict(a, i) for a, i in rows]}


async def add_asset(db: AsyncSession, project_id: int, request: AssetAdd) -> dict:
    await get_project(db, project_id)
    item = await db.get(LibraryItem, request.library_item_id)
    if not item:
        raise NotFoundError("灵感库条目", request.library_item_id)
    same = (
        (
            await db.execute(
                select(ProjectAsset).where(
                    ProjectAsset.project_id == project_id,
                    ProjectAsset.library_item_id == request.library_item_id,
                    ProjectAsset.role == request.role,
                )
            )
        )
        .scalars()
        .all()
    )
    for a in same:
        if (a.target or None) == (request.target or None):
            return _asset_dict(a, item)
    if request.role == "moodboard":
        count = (
            await db.execute(
                select(func.count())
                .select_from(ProjectAsset)
                .where(ProjectAsset.project_id == project_id, ProjectAsset.role == "moodboard")
            )
        ).scalar_one()
        if count >= MAX_MOODBOARD:
            raise ValidationError(f"情绪板最多 {MAX_MOODBOARD} 项")
    asset = ProjectAsset(
        project_id=project_id, library_item_id=item.id, role=request.role, target=request.target or None
    )
    db.add(asset)
    await db.commit()
    return _asset_dict(asset, item)


async def remove_asset(db: AsyncSession, project_id: int, asset_id: int) -> None:
    asset = await db.get(ProjectAsset, asset_id)
    if not asset or asset.project_id != project_id:
        raise NotFoundError("项目素材", asset_id)
    await db.delete(asset)
    await db.commit()


# ── 开始写稿 ─────────────────────────────────────────────────────────


async def generate_draft(db: AsyncSession, project_id: int, mode: str) -> dict:
    """blank：空文稿；template：按内容模板生成骨架（compile_draft）。ai 模式走成稿流程（runs）。"""
    from app.services.studio_catalog import catalog_for_user, compile_draft, resolve

    if mode == "ai":
        from app.services.draft_flow import start_ai_draft

        return await start_ai_draft(db, project_id)
    project = await get_project(db, project_id, lock=True)
    if project.finalized_version:
        raise conflict("finalized", "已定稿，点「继续修改」后才能重写")
    spec = deepcopy(project.spec or {})
    brief = studio_brief(spec.get("brief", {}))
    if not copy_brief(spec.get("brief")).get("theme"):
        raise ValidationError("先写一个主题")
    if mode == "blank":
        if project.stage == "idea":
            project.stage = "draft"
        await db.commit()
        return await draft_view(db, project_id)
    catalog = await catalog_for_user(db, project.owner_id)
    template, _style = resolve(brief, templates=catalog["templates"], styles=catalog["styles"])
    spec["template"] = template
    project.spec = spec
    previous = StudioDraft.model_validate(spec.get("draft") or {})
    draft = compile_draft(brief, previous, template)
    await db.flush()
    await write_draft_version(db, project_id, draft, "compiled")
    return await draft_view(db, project_id)


def _pipeline_view(spec: dict) -> dict:
    from app.services.pipeline_service import view

    return view(spec)


# ── 创意方向 ─────────────────────────────────────────────────────────


async def start_directions(db: AsyncSession, project_id: int, *, choose_gate: bool = False) -> dict:
    """启动选题研究流程（研究员 → 汇总 → 策划）；默认不停在关卡，方向卡由前端从运行产物读取。全流程会保留关卡。"""
    from app.services.flows import engine

    project = await get_project(db, project_id)
    spec = deepcopy(project.spec or {})
    brief = copy_brief(spec.get("brief"))
    sources = await list_sources(db, project_id)
    topic = brief.get("theme") or next((s["snapshot"].get("title") for s in sources if s["role"] == "main"), "")
    if not topic:
        raise ValidationError("先挑一个来源或写一个主题")
    try:
        run = await engine.start_run(
            db,
            "topic_research",
            {
                "topic": topic,
                "content_ids": [s["content_id"] for s in sources if s["content_id"]],
                "notes": brief.get("intent") or None,
            },
            title=f"方向 · {topic}"[:300],
            gates={"choose": choose_gate},
            project_id=project_id,
            trigger="project",
        )
    except engine.FlowError as exc:
        raise AppException(str(exc), 503, {"code": "model_unavailable"}) from exc
    project = await get_project(db, project_id)
    spec = deepcopy(project.spec or {})
    spec["idea"] = {**(spec.get("idea") or {}), "run_id": run.id}
    project.spec = spec
    await db.commit()
    return {"run_id": run.id}
