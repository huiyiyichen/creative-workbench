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
from app.models.studio import StudioProject

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


async def ensure_version_artifact(db: AsyncSession, project: StudioProject, version: int) -> Artifact:
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
