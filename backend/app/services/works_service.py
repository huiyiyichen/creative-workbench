"""作品库（改造方案 9）：按项目归档产出物，可预览、下载、复制。

收录规则：完成 / 已导出 / 已发布的产出物、已生成正文的平台版本自动收录；其他草稿可以手动「加入作品库」
（`settings.in_works = true`）；`in_works = false` 表示从作品库移出。旧工作台做的成片（没有挂在产出物上的
完成制作物）作为「旧成片」一并列出。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectArtifact, ProjectOutput
from app.services import project_service as ps

AUTO_STATUSES = ("done", "exported", "published")
PLATFORM_KINDS = ("xhs", "zhihu", "wechat", "bilibili", "douyin")
RENDER_KINDS = ("video", "mv")


def included(output: ProjectOutput) -> bool:
    flag = (output.settings or {}).get("in_works")
    if flag is False:
        return False
    if flag or output.status in AUTO_STATUSES:
        return True
    # 平台版本生成出正文就算一件作品（之前停在「草稿」要手点加入，用户以为是 bug）
    return output.kind in PLATFORM_KINDS and bool(str((output.content or {}).get("body") or "").strip())


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _excerpt(content: dict[str, Any]) -> str:
    body = content.get("body") or content.get("markdown") or content.get("summary") or ""
    return _plain(str(body))[:140]


def _copy_text(output: ProjectOutput) -> str | None:
    c = output.content or {}
    if output.kind in PLATFORM_KINDS:
        parts = [
            str(c.get("title") or ""),
            _plain(str(c.get("body") or "")) if output.kind == "wechat" else str(c.get("body") or ""),
        ]
        tags = c.get("tags") or []
        if tags:
            parts.append(" ".join(f"#{t}" for t in tags))
        return "\n\n".join(p for p in parts if p).strip() or None
    if output.kind == "prompt_bundle":
        return str(c.get("markdown") or "") or None
    return None


async def list_works(
    db: AsyncSession, *, q: str | None = None, kind: str | None = None, project_id: int | None = None
) -> dict[str, Any]:
    from app.services.studio_service import artifact_dict

    stmt = select(ProjectOutput).order_by(ProjectOutput.updated_at.desc())
    if project_id is not None:
        stmt = stmt.where(ProjectOutput.project_id == project_id)
    outputs = [o for o in (await db.execute(stmt)).scalars().all() if included(o)]
    if kind:
        outputs = [o for o in outputs if o.kind == kind]
    art_stmt = select(ProjectArtifact).where(ProjectArtifact.status == "done").order_by(ProjectArtifact.id.desc())
    if project_id is not None:
        art_stmt = art_stmt.where(ProjectArtifact.project_id == project_id)
    arts = (await db.execute(art_stmt)).scalars().all()
    latest: dict[int, ProjectArtifact] = {}
    legacy: list[ProjectArtifact] = []
    for a in arts:
        if a.output_id:
            latest.setdefault(a.output_id, a)
        elif a.relative_path and (kind in (None, "", "video", "legacy")):
            legacy.append(a)
    pids = {o.project_id for o in outputs} | {a.project_id for a in legacy}
    projects = {}
    if pids:
        projects = {p.id: p for p in (await db.execute(select(Project).where(Project.id.in_(pids)))).scalars()}
    groups: dict[int, dict[str, Any]] = {}

    def group(pid: int) -> dict[str, Any]:
        if pid not in groups:
            p = projects.get(pid)
            groups[pid] = {
                "project": {
                    "id": pid,
                    "title": p.title if p else f"项目 {pid}",
                    "archived": bool(getattr(p, "archived_at", None)) if p else False,
                },
                "items": [],
            }
        return groups[pid]

    for o in outputs:
        art = latest.get(o.id)
        media = artifact_dict(art) if art else None
        group(o.project_id)["items"].append(
            {
                "key": f"output:{o.id}",
                "type": "output",
                "id": o.id,
                "kind": o.kind,
                "title": o.title or ps.OUTPUT_TITLES.get(o.kind, o.kind),
                "status": o.status,
                "based_on_version": o.based_on_version,
                "excerpt": _excerpt(o.content or {}),
                "chars": len(_plain(str((o.content or {}).get("body") or ""))) or None,
                "copy_text": _copy_text(o),
                "cover": (o.content or {}).get("cover_url"),
                "preview_path": media["preview_path"] if media else None,
                "download_path": media["download_path"] if media else None,
                "published_url": o.published_url,
                "schedule": (o.settings or {}).get("schedule"),
                "metrics": ((o.settings or {}).get("metrics") or {}).get("latest") or {},
                "manual": (o.settings or {}).get("in_works") is True,
                "href": f"/projects/{o.project_id}/outputs/{o.id}",
                "updated_at": ps._iso(o.updated_at),
            }
        )
    for a in legacy:
        d = artifact_dict(a)
        group(a.project_id)["items"].append(
            {
                "key": f"artifact:{a.id}",
                "type": "legacy",
                "id": a.id,
                "kind": a.kind,
                "title": f"旧成片 v{a.version}",
                "status": "done",
                "based_on_version": a.version,
                "excerpt": "",
                "chars": None,
                "copy_text": None,
                "cover": None,
                "preview_path": d["preview_path"],
                "download_path": d["download_path"],
                "published_url": None,
                "manual": False,
                "href": f"/projects/{a.project_id}/outputs",
                "updated_at": d["created_at"],
            }
        )
    items = list(groups.values())
    if q:
        needle = q.strip().lower()
        for g in items:
            if needle in g["project"]["title"].lower():
                continue
            g["items"] = [i for i in g["items"] if needle in (i["title"] + " " + i["excerpt"]).lower()]
        items = [g for g in items if g["items"]]
    items.sort(key=lambda g: max((i["updated_at"] or "") for i in g["items"]), reverse=True)
    return {"groups": items, "total": sum(len(g["items"]) for g in items)}


async def set_in_works(db: AsyncSession, output_id: int, value: bool) -> dict:
    output = await ps.get_output(db, output_id)
    output.settings = {**(output.settings or {}), "in_works": bool(value)}
    await db.commit()
    return await ps.output_view(db, output_id)
