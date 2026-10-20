"""「生成平台版本」：启动平台改写流程（平台编辑并行 → 规则校验，写入平台版本产出物）。"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ValidationError
from app.models.agent_run import AgentRun
from app.schemas.studio import StudioDraft
from app.services import project_service as ps
from app.services.output_rules import PLATFORM_RULES

ACTIVE = ("queued", "running", "waiting", "paused")


async def start_platform_rewrite(
    db: AsyncSession, project_id: int, kinds: list[str], output_ids: dict[str, int] | None = None
) -> dict:
    from app.services import output_service as outs
    from app.services.flows import engine

    kinds = [k for k in dict.fromkeys(kinds) if k in PLATFORM_RULES]
    if not kinds:
        raise ValidationError("至少选一个平台")
    project = await ps.get_project(db, project_id)
    spec, _version = await outs.base_spec(db, project)
    if not StudioDraft.model_validate(spec.get("draft") or {}).body.strip():
        raise ValidationError("文稿是空的，先写稿")
    running = ((project.spec or {}).get("platform_rewrite") or {}).get("run_id")
    if running:
        prev = await db.get(AgentRun, running)
        if prev and prev.status in ACTIVE:
            return {"run_id": prev.id, "status": prev.status}
    try:
        run = await engine.start_run(
            db,
            "platform_rewrite",
            {
                "project_id": str(project_id),
                "platforms": kinds,
                "output_ids": {k: int(v) for k, v in (output_ids or {}).items() if k in kinds and v},
            },
            title=f"平台改写 · {project.title}"[:300],
            project_id=project_id,
            trigger="project",
        )
    except engine.FlowError as exc:
        raise AppException(str(exc), 503, {"code": "model_unavailable"}) from exc
    project = await ps.get_project(db, project_id)
    data = deepcopy(project.spec or {})
    data["platform_rewrite"] = {"run_id": run.id, "status": run.status, "kinds": kinds}
    project.spec = data
    if project.stage in ("idea", "draft") and project.finalized_version:
        project.stage = "outputs"
    await db.commit()
    return {"run_id": run.id, "status": run.status}


async def on_run_finished(db: AsyncSession, run: AgentRun) -> None:
    if not run.project_id:
        return
    project = await ps.get_project(db, run.project_id)
    data = deepcopy(project.spec or {})
    cur = data.get("platform_rewrite") or {}
    if cur.get("run_id") != run.id:
        return
    data["platform_rewrite"] = {**cur, "status": run.status, "reason": run.status_reason}
    project.spec = data
    await db.commit()
