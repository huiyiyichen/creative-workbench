"""项目产物的溯源登记（创作工作台设计 7.2）。

文稿版本登记成产物（kind=draft_version，content.version），带段落锚点的来源：
* 版本来自成稿流程时，沿用写手登记的段落引用（apply_draft 已经建过这个产物）；
* 手写 / 改过的版本：正文里的「[n]」按第 n 个来源登记到所在段落；没有标注时整体引用主来源。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import Artifact
from app.models.project import Project

_CITE = re.compile(r"\[(\d{1,2})\]")


async def find_version_artifact(db: AsyncSession, project_id: int, version: int) -> Artifact | None:
    rows = (
        await db.execute(
            select(Artifact)
            .where(Artifact.project_id == project_id, Artifact.kind == "draft_version")
            .order_by(Artifact.id.desc())
        )
    ).scalars()
    for a in rows:
        if (a.content or {}).get("version") == version:
            return a
    return None


def marker_links(body: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.services.flows.roles_draft import source_link
    from app.services.project_service import paragraphs_with_ids

    links = []
    for p in paragraphs_with_ids(body):
        for n in dict.fromkeys(int(x) for x in _CITE.findall(p["text"])):
            if 1 <= n <= len(sources):
                ln = source_link(sources[n - 1], p["id"])
                if ln:
                    links.append(ln)
    return links


async def ensure_version_artifact(db: AsyncSession, project: Project, version: int) -> Artifact:
    from app.services import project_service as ps, trace_service

    found = await find_version_artifact(db, project.id, version)
    if found is not None:
        return found
    rev = await ps._revision(db, project.id, version)
    draft = (rev.spec or {}).get("draft") or {}
    sources = await ps.list_sources(db, project.id)
    links = marker_links(draft.get("body") or "", sources)
    if not links:
        from app.services.flows.roles_draft import source_link

        main = next((s for s in sources if s["role"] == "main"), None)
        ln = source_link(main, None) if main else None
        if ln:
            links.append(ln)
    return await trace_service.add_artifact(
        db,
        kind="draft_version",
        title=f"文稿 v{version}",
        content={"project_id": project.id, "version": version, "title": draft.get("title"), "reason": rev.reason},
        project_id=project.id,
        links=links,
    )


async def register_platform(db: AsyncSession, output, content: dict[str, Any], version: int | None) -> Artifact | None:
    """平台稿登记为产物：平台稿 ← 文稿版本 ← 来源（段落锚点沿用版本的）。"""
    from app.services import project_service as ps, trace_service

    if not version:
        return None
    project = await ps.get_project(db, output.project_id)
    version_art = await ensure_version_artifact(db, project, version)
    return await trace_service.add_artifact(
        db,
        kind=f"platform_{output.kind}",
        title=(content.get("title") or output.title or "平台稿")[:300],
        content={
            "output_id": output.id,
            "version": version,
            "title": content.get("title"),
            "chars": len(content.get("body") or ""),
        },
        project_id=output.project_id,
        links=[{"relation": "derived_from", "target_type": "artifact", "target_id": version_art.id}],
    )


async def _latest(db: AsyncSession, project_id: int, kinds: list[str], match) -> Artifact | None:
    rows = (
        await db.execute(
            select(Artifact)
            .where(Artifact.project_id == project_id, Artifact.kind.in_(kinds))
            .order_by(Artifact.id.desc())
        )
    ).scalars()
    for a in rows:
        if match(a.content or {}):
            return a
    return None


async def resolve(
    db: AsyncSession,
    *,
    target: str,
    project_id: int | None = None,
    version: int | None = None,
    anchor: str | None = None,
    output_id: int | None = None,
    studio_artifact_id: int | None = None,
    shot: int | None = None,
) -> tuple[Artifact, str | None]:
    """界面上的溯源入口 → (产物, 锚点)。

    paragraph：文稿版本（没有登记过就登记）+ 段落 id；version：整个版本；
    shot：该产出物最近一次分镜 + ``shot_N``；video：成片（按 ProjectArtifact）；platform：平台稿最新一次。
    """
    from app.core.exceptions import NotFoundError, ValidationError
    from app.services import project_service as ps

    if target in ("paragraph", "version"):
        if not project_id:
            raise ValidationError("缺少项目")
        project = await ps.get_project(db, project_id)
        v = version or project.finalized_version or project.version
        art = await ensure_version_artifact(db, project, v)
        return art, (anchor if target == "paragraph" else None)
    if target in ("shot", "video", "platform"):
        if not output_id:
            raise ValidationError("缺少产出物")
        output = await ps.get_output(db, output_id)
        pid = output.project_id
        if target == "shot":
            art = await _storyboard_for_output(db, pid, output_id)
            if art is None:
                raise NotFoundError("分镜产物", output_id)
            return art, f"shot_{shot}" if shot else None
        if target == "video":
            art = await _latest(
                db,
                pid,
                ["video"],
                lambda c: studio_artifact_id is None or c.get("studio_artifact_id") == studio_artifact_id,
            )
            if art is None:
                raise NotFoundError("成片产物", studio_artifact_id or output_id)
            return art, None
        art = await _latest(db, pid, [f"platform_{output.kind}"], lambda c: c.get("output_id") == output_id)
        if art is None:
            v = output.based_on_version
            if not v:
                raise NotFoundError("平台稿产物", output_id)
            art = await register_platform(db, output, output.content or {}, v)
        return art, None
    raise ValidationError(f"未知的溯源入口 {target}")


async def _storyboard_for_output(db: AsyncSession, project_id: int, output_id: int) -> Artifact | None:
    from app.models.agent_run import AgentRun

    rows = (
        await db.execute(
            select(Artifact)
            .join(AgentRun, AgentRun.id == Artifact.run_id)
            .where(Artifact.project_id == project_id, Artifact.kind == "storyboard")
            .order_by(Artifact.id.desc())
        )
    ).scalars()
    for a in rows:
        run = await db.get(AgentRun, a.run_id)
        if run and str((run.inputs or {}).get("output_id")) == str(output_id):
            return a
    return None
