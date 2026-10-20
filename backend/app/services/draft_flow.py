"""「AI 写初稿」：启动成稿流程（写手 → 审校 → 写手修改 →〔接受〕→ 写入文稿）。"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ValidationError
from app.models.agent_run import AgentRun
from app.services import project_service as ps


async def start_ai_draft(db: AsyncSession, project_id: int, *, review_gate: bool = False) -> dict:
    """review_gate=False 时关卡关闭：修改稿直接写成新版本（旧版本都在「版本」里，可以恢复）。"""
    from app.services.flows import engine

    project = await ps.get_project(db, project_id)
    if project.finalized_version:
        raise ps.conflict("finalized", "已定稿，点「继续修改」后才能重写")
    brief = ps.copy_brief((project.spec or {}).get("brief"))
    if not brief.get("theme"):
        raise ValidationError("先写一个主题")
    running = ((project.spec or {}).get("ai_draft") or {}).get("run_id")
    if running:
        prev = await db.get(AgentRun, running)
        if prev and prev.status in ("queued", "running", "waiting"):
            return {"run_id": prev.id, "status": prev.status}
    try:
        run = await engine.start_run(
            db,
            "draft_writing",
            {"project_id": str(project_id), "topic": brief["theme"]},
            title=f"成稿 · {brief['theme']}"[:300],
            gates={"accept": review_gate},
            project_id=project_id,
            trigger="project",
        )
    except engine.FlowError as exc:
        raise AppException(str(exc), 503, {"code": "model_unavailable"}) from exc
    project = await ps.get_project(db, project_id)
    spec = deepcopy(project.spec or {})
    spec["ai_draft"] = {"run_id": run.id, "status": run.status}
    project.spec = spec
    if project.stage == "idea":
        project.stage = "draft"
    await db.commit()
    return {"run_id": run.id, "status": run.status}


async def on_run_finished(db: AsyncSession, run: AgentRun) -> None:
    if not run.project_id:
        return
    project = await ps.get_project(db, run.project_id)
    spec = deepcopy(project.spec or {})
    if (spec.get("ai_draft") or {}).get("run_id") != run.id:
        return
    spec["ai_draft"] = {"run_id": run.id, "status": run.status, "reason": run.status_reason}
    project.spec = spec
    await db.commit()
