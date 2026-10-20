"""一键全流程（改造方案 2.2）：选题研究 →〔选方向〕→ 成稿 →〔接受〕→〔定稿〕→ 讲解视频 + 平台改写。

各段是独立的流程运行，用项目上的 `spec.pipeline` 串起来：每段结束时（引擎的结束回调）推进到下一段；
定稿始终由你确认，定稿后自动开始制作和平台改写。人工关卡默认保留，可在启动时关闭「选方向」「接受」。
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.agent_run import AgentRun, Artifact
from app.services import project_service as ps

logger = logging.getLogger(__name__)

PLATFORM_KINDS = ("xhs", "zhihu", "wechat")
RENDER_KINDS = ("video",)
STAGE_LABELS = {
    "research": "选题研究",
    "draft": "成稿",
    "awaiting_finalize": "等你定稿",
    "producing": "制作与平台改写",
    "done": "完成",
    "failed": "失败",
    "stopped": "已停止",
}
NOTIFY = True


def _now() -> str:
    return datetime.now(UTC).isoformat()


def view(spec: dict | None) -> dict:
    p = dict((spec or {}).get("pipeline") or {})
    if p:
        p["stage_label"] = STAGE_LABELS.get(p.get("stage") or "", p.get("stage"))
    return p


async def _save(db: AsyncSession, project, pipeline: dict) -> None:
    data = deepcopy(project.spec or {})
    data["pipeline"] = {**pipeline, "updated_at": _now()}
    project.spec = data
    await db.commit()


async def _fail(db: AsyncSession, project, pipeline: dict, reason: str) -> None:
    await _save(db, project, {**pipeline, "stage": "failed", "reason": reason[:500]})
    await _notify(project, f"全流程停在「{STAGE_LABELS.get(pipeline.get('stage'), '')}」：{reason[:120]}")


async def _notify(project, message: str) -> None:
    if not NOTIFY:
        return
    try:
        from app.services import notification_service

        await notification_service.push_notification("pipeline", "project", f"项目 · {project.title}"[:120], message)
    except Exception:  # noqa: BLE001
        logger.debug("pipeline notify skipped", exc_info=True)


async def start(
    db: AsyncSession,
    project_id: int,
    *,
    outputs: list[str] | None = None,
    choose_gate: bool = True,
    accept_gate: bool = True,
) -> dict:
    project = await ps.get_project(db, project_id)
    if project.finalized_version:
        raise ps.conflict("finalized", "已定稿：全流程从选题开始，点「继续修改」解锁后再启动，或直接在产出里制作")
    current = view(project.spec)
    if current.get("stage") in ("research", "draft", "awaiting_finalize", "producing"):
        return current
    wanted = [k for k in dict.fromkeys(outputs or ["video", *PLATFORM_KINDS]) if k in (*RENDER_KINDS, *PLATFORM_KINDS)]
    if not wanted:
        raise ValidationError("至少选一种产出")
    res = await ps.start_directions(db, project_id, choose_gate=choose_gate)
    project = await ps.get_project(db, project_id)
    pipeline = {
        "stage": "research",
        "outputs": wanted,
        "gates": {"choose": choose_gate, "accept": accept_gate},
        "runs": {"research": res["run_id"]},
        "started_at": _now(),
        "reason": None,
    }
    await _save(db, project, pipeline)
    return view(project.spec)


async def stop(db: AsyncSession, project_id: int) -> dict:
    from app.services.flows import engine

    project = await ps.get_project(db, project_id)
    pipeline = view(project.spec)
    if not pipeline or pipeline.get("stage") in ("done", "failed", "stopped"):
        return pipeline
    for rid in (pipeline.get("runs") or {}).values():
        for one in rid if isinstance(rid, list) else [rid]:
            run = await db.get(AgentRun, one)
            if run and run.status in ("queued", "running", "waiting", "paused"):
                try:
                    await engine.stop_run(db, run.id)
                except Exception:  # noqa: BLE001
                    logger.debug("stop run %s failed", one, exc_info=True)
    project = await ps.get_project(db, project_id)
    await _save(db, project, {**view(project.spec), "stage": "stopped", "reason": "你停止了全流程"})
    return view(project.spec)


async def _chosen_direction(db: AsyncSession, run: AgentRun) -> dict[str, str] | None:
    """选方向关卡的结果；关卡关闭时取第一张方向卡。"""
    decision = ((run.outputs or {}).get("decisions") or {}).get("choose") or {}
    if decision.get("custom"):
        return {"title": decision["custom"].split("\n")[0][:120], "intent": decision["custom"]}
    art_id = decision.get("artifact_id")
    card_id = decision.get("card_id")
    art = None
    if art_id:
        art = await db.get(Artifact, int(art_id))
    if art is None:
        from sqlalchemy import select

        art = (
            await db.execute(
                select(Artifact)
                .where(Artifact.run_id == run.id, Artifact.kind == "direction_cards")
                .order_by(Artifact.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    cards = ((art.content if art else None) or {}).get("cards") or []
    card = next((c for c in cards if c.get("id") == card_id), None) if card_id else (cards[0] if cards else None)
    if not card:
        return None
    intent = "\n".join(x for x in (card.get("angle"), card.get("why_now")) if x)
    return {"title": str(card.get("title") or "")[:120], "intent": intent}


async def _apply_direction(db: AsyncSession, project, direction: dict[str, str]) -> None:
    data = deepcopy(project.spec or {})
    brief = ps.copy_brief(data.get("brief"))
    brief["theme"] = direction["title"] or brief.get("theme") or project.title
    if direction.get("intent"):
        brief["intent"] = direction["intent"]
    data["brief"] = brief
    project.spec = data
    await db.commit()


async def on_run_finished(db: AsyncSession, run: AgentRun) -> None:
    """任何流程运行结束时调用：属于某个项目的全流程就推进一步。"""
    if not run.project_id:
        return
    project = await ps.get_project(db, run.project_id)
    pipeline = view(project.spec)
    runs = pipeline.get("runs") or {}
    stage = pipeline.get("stage")
    if stage == "research" and runs.get("research") == run.id:
        if run.status != "done":
            return await _fail(db, project, pipeline, run.status_reason or f"选题研究{run.status}")
        direction = await _chosen_direction(db, run)
        if not direction:
            return await _fail(db, project, pipeline, "没有可用的方向卡")
        await _apply_direction(db, project, direction)
        from app.services import draft_flow

        try:
            res = await draft_flow.start_ai_draft(
                db, project.id, review_gate=bool((pipeline.get("gates") or {}).get("accept", True))
            )
        except Exception as exc:  # noqa: BLE001
            project = await ps.get_project(db, run.project_id)
            return await _fail(db, project, pipeline, f"成稿没有启动：{exc}")
        project = await ps.get_project(db, run.project_id)
        await _save(
            db,
            project,
            {**pipeline, "stage": "draft", "direction": direction, "runs": {**runs, "draft": res["run_id"]}},
        )
        return None
    if stage == "draft" and runs.get("draft") == run.id:
        if run.status != "done":
            return await _fail(db, project, pipeline, run.status_reason or f"成稿{run.status}")
        rejected = (((run.outputs or {}).get("decisions") or {}).get("accept") or {}).get("card_id") == "reject"
        await _save(db, project, {**pipeline, "stage": "awaiting_finalize", "draft_rejected": rejected})
        await _notify(project, "初稿写好了，看一遍后定稿；定稿后自动开始制作和平台改写。")
        return None
    if stage == "producing":
        await _check_produced(db, project, pipeline)
    return None


async def on_finalized(db: AsyncSession, project_id: int) -> None:
    """定稿后：如果全流程在等定稿，就开始制作和平台改写。"""
    project = await ps.get_project(db, project_id)
    pipeline = view(project.spec)
    if pipeline.get("stage") != "awaiting_finalize":
        return
    from app.schemas.projects import OutputCreate
    from app.services import platform_flow, production_service

    runs = dict(pipeline.get("runs") or {})
    problems: list[str] = []
    wanted = pipeline.get("outputs") or []
    for kind in [k for k in wanted if k in RENDER_KINDS]:
        try:
            out = await ps.create_output(db, project_id, OutputCreate(kind=kind))
            res = await production_service.start_render(db, out["id"])
            runs.setdefault("produce", []).append(res["run_id"])
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            problems.append(f"{ps.OUTPUT_TITLES.get(kind, kind)}：{getattr(exc, 'message', None) or exc}")
    kinds = [k for k in wanted if k in PLATFORM_KINDS]
    if kinds:
        try:
            res = await platform_flow.start_platform_rewrite(db, project_id, kinds)
            runs["platforms"] = res["run_id"]
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            problems.append(f"平台改写：{getattr(exc, 'message', None) or exc}")
    project = await ps.get_project(db, project_id)
    if not runs.get("produce") and not runs.get("platforms"):
        return await _fail(db, project, {**pipeline, "runs": runs}, "；".join(problems) or "没有可开始的产出")
    await _save(db, project, {**pipeline, "stage": "producing", "runs": runs, "problems": problems})
    project = await ps.get_project(db, project_id)
    await _check_produced(db, project, view(project.spec))


async def _check_produced(db: AsyncSession, project, pipeline: dict) -> None:
    runs = pipeline.get("runs") or {}
    ids: list[int] = list(runs.get("produce") or []) + ([runs["platforms"]] if runs.get("platforms") else [])
    statuses: list[str] = []
    for rid in ids:
        run = await db.get(AgentRun, rid, populate_existing=True)
        statuses.append(run.status if run else "failed")
    if any(s in ("queued", "running", "waiting", "paused") for s in statuses):
        return
    failed = [s for s in statuses if s != "done"]
    problems = list(pipeline.get("problems") or [])
    if failed or problems:
        reason = "；".join(problems + ([f"{len(failed)} 个运行没有完成"] if failed else []))
        await _save(db, project, {**pipeline, "stage": "done", "reason": reason, "partial": True})
        await _notify(project, f"全流程结束，有部分没完成：{reason[:120]}")
    else:
        await _save(db, project, {**pipeline, "stage": "done", "reason": None})
        await _notify(project, "全流程完成：成片和平台版本都在「产出」里。")


def summary(spec: dict | None) -> dict[str, Any]:
    return view(spec)
