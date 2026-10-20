"""任务中心（创作工作台设计 7）：流程运行、生图 / 生成任务、信源采集、内容分析合成一张任务表。

每行统一成 TaskView：type、标题、项目 / 产出物、状态（running / waiting / failed / done / stopped）、
当前阶段、开始时间、耗时、花费、失败原因和处理建议、跳转链接。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun, AgentStep
from app.models.analysis_job import AnalysisJobRecord
from app.models.generation import GenerationJob
from app.models.source import Source
from app.models.source_sync_run import SourceSyncRun
from app.models.studio import StudioOutput, StudioProject

TYPES = ("flow", "generation", "sync", "analysis")
STATUSES = ("running", "waiting", "failed", "done", "stopped")
FLOW_LABEL = {
    "topic_research": "选题研究",
    "draft_writing": "成稿",
    "video_production": "成片",
    "platform_rewrite": "平台改写",
}
_RUN_STATUS = {
    "queued": "running",
    "running": "running",
    "waiting": "waiting",
    "paused": "waiting",
    "failed": "failed",
    "done": "done",
    "stopped": "stopped",
}
_SYNC_STATUS = {"running": "running", "success": "done", "empty": "done", "failed": "failed", "skipped": "stopped"}
_GEN_STATUS = {"queued": "running", "running": "running", "done": "done", "failed": "failed"}
_ANALYSIS_STATUS = {
    "queued": "running",
    "pending": "running",
    "running": "running",
    "done": "done",
    "completed": "done",
    "success": "done",
    "failed": "failed",
    "cancelled": "stopped",
}
# 失败时给出「怎么处理」
_HINTS = (
    ("超时", "可以重试；已完成的步骤会复用"),
    ("预算", "追加预算后继续"),
    ("未安装", "到「设置 · 生成服务」检查执行者"),
    ("验证码", "到信源页重新登录该平台"),
    ("api key", "到设置里检查服务的 API Key"),
    ("401", "到设置里检查服务的 API Key"),
    ("429", "被限流，稍后重试"),
)


def _ms(a: datetime | None, b: datetime | None) -> int | None:
    if a is None:
        return None
    end = b or datetime.now(UTC)
    if a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return max(0, int((end - a).total_seconds() * 1000))


def hint(reason: str | None) -> str | None:
    if not reason:
        return None
    low = reason.lower()
    return next((h for k, h in _HINTS if k in low), "可以重试，或打开详情查看过程")


def _row(**kw: Any) -> dict[str, Any]:
    kw.setdefault("project_id", None)
    kw.setdefault("project_title", None)
    kw.setdefault("output_title", None)
    kw.setdefault("stage", None)
    kw.setdefault("cost", 0.0)
    kw.setdefault("reason", None)
    kw["hint"] = hint(kw["reason"]) if kw["status"] == "failed" else None
    kw["duration_ms"] = _ms(kw.get("started_at"), kw.get("finished_at"))
    return kw


async def _runs(db: AsyncSession, since: datetime, limit: int) -> list[dict[str, Any]]:
    runs = (
        (
            await db.execute(
                select(AgentRun).where(AgentRun.created_at >= since).order_by(AgentRun.id.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not runs:
        return []
    ids = [r.id for r in runs]
    current: dict[int, str] = {}
    for s in (
        await db.execute(
            select(AgentStep)
            .where(AgentStep.run_id.in_(ids), AgentStep.status.in_(["running", "waiting"]))
            .order_by(AgentStep.id)
        )
    ).scalars():
        current[s.run_id] = s.label + ("（等你处理）" if s.status == "waiting" else "")
    out_ids = {int(o) for r in runs if (o := (r.inputs or {}).get("output_id")) and str(o).isdigit()}
    outputs = {}
    if out_ids:
        outputs = {
            o.id: o.title
            for o in (await db.execute(select(StudioOutput).where(StudioOutput.id.in_(out_ids)))).scalars()
        }
    rows = []
    for r in runs:
        oid = (r.inputs or {}).get("output_id")
        rows.append(
            _row(
                key=f"flow:{r.id}",
                type="flow",
                kind=r.flow_key,
                kind_label=FLOW_LABEL.get(r.flow_key, r.flow_key),
                title=r.title,
                project_id=r.project_id,
                output_title=outputs.get(int(oid)) if oid and str(oid).isdigit() else None,
                status=_RUN_STATUS.get(r.status, r.status),
                raw_status=r.status,
                stage=(f"已暂停：{r.status_reason}" if r.status_reason else "已暂停")
                if r.status == "paused"
                else current.get(r.id),
                created_at=r.created_at,
                started_at=r.started_at or r.created_at,
                finished_at=r.finished_at,
                cost=float(r.cost or 0),
                reason=r.status_reason,
                href=f"/runs/{r.id}",
                can_stop=r.status in ("queued", "running", "waiting", "paused"),
                can_retry=r.status in ("failed", "paused"),
            )
        )
    return rows


async def _generations(db: AsyncSession, since: datetime, limit: int) -> list[dict[str, Any]]:
    jobs = (
        (
            await db.execute(
                select(GenerationJob)
                .where(GenerationJob.created_at >= since)
                .order_by(GenerationJob.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rows = []
    for j in jobs:
        n = len(j.results or [])
        rows.append(
            _row(
                key=f"generation:{j.id}",
                type="generation",
                kind=j.kind,
                kind_label={"image": "生图", "video": "生成视频", "music": "生成音乐"}.get(j.kind, j.kind),
                title=(j.prompt or "")[:80] or f"生成 #{j.id}",
                project_id=j.project_id,
                status=_GEN_STATUS.get(j.status, j.status),
                raw_status=j.status,
                stage=(f"{n} 个结果" if n else None)
                if j.kind != "video" or j.status not in ("queued", "running")
                else f"厂商生成中 {int((j.params or {}).get('progress') or 0)}%",
                created_at=j.created_at,
                started_at=j.created_at,
                finished_at=j.finished_at,
                cost=float(j.cost or 0),
                reason=j.error,
                href=f"/projects/{j.project_id}/idea" if j.project_id else "/settings/generation",
                can_stop=False,
                can_retry=False,
            )
        )
    return rows


async def _syncs(db: AsyncSession, since: datetime, limit: int) -> list[dict[str, Any]]:
    rows_db = (
        await db.execute(
            select(SourceSyncRun, Source.name)
            .join(Source, Source.id == SourceSyncRun.source_id)
            .where(SourceSyncRun.started_at >= since)
            .order_by(SourceSyncRun.id.desc())
            .limit(limit)
        )
    ).all()
    rows = []
    for s, name in rows_db:
        stage = None
        if s.status in ("success", "empty"):
            stage = f"抓到 {s.fetched or 0} 条，新增 {s.new or 0}"
        rows.append(
            _row(
                key=f"sync:{s.id}",
                type="sync",
                kind=s.trigger,
                kind_label="采集",
                title=name,
                status=_SYNC_STATUS.get(s.status, s.status),
                raw_status=s.status,
                stage=stage,
                created_at=s.started_at,
                started_at=s.started_at,
                finished_at=s.finished_at,
                reason=s.error_message,
                href=f"/sources?source={s.source_id}",
                can_stop=False,
                can_retry=False,
            )
        )
    return rows


async def _analyses(db: AsyncSession, since: datetime, limit: int) -> list[dict[str, Any]]:
    jobs = (
        (
            await db.execute(
                select(AnalysisJobRecord)
                .where(AnalysisJobRecord.queued_at >= since)
                .order_by(AnalysisJobRecord.queued_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rows = []
    for j in jobs:
        total = len(j.content_ids or [])
        done = len(j.analyzed_ids or [])
        failed = len(j.failed_ids or [])
        rows.append(
            _row(
                key=f"analysis:{j.job_id}",
                type="analysis",
                kind="analysis",
                kind_label="内容分析",
                title=f"分析 {total} 条内容",
                status=_ANALYSIS_STATUS.get(j.status, j.status),
                raw_status=j.status,
                stage=f"{done} / {total}" + (f"，失败 {failed}" if failed else ""),
                created_at=j.queued_at,
                started_at=j.started_at or j.queued_at,
                finished_at=j.finished_at,
                reason=j.error_message,
                href="/stats/jobs",
                can_stop=False,
                can_retry=False,
            )
        )
    return rows


async def list_tasks(
    db: AsyncSession,
    *,
    types: list[str] | None = None,
    status: str | None = None,
    project_id: int | None = None,
    days: int = 7,
    limit: int = 100,
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 90)))
    want = [t for t in (types or TYPES) if t in TYPES]
    per = max(10, min(limit, 300))
    rows: list[dict[str, Any]] = []
    if "flow" in want:
        rows += await _runs(db, since, per)
    if "generation" in want:
        rows += await _generations(db, since, per)
    if "sync" in want:
        rows += await _syncs(db, since, per)
    if "analysis" in want:
        rows += await _analyses(db, since, per)
    pids = {r["project_id"] for r in rows if r["project_id"]}
    if pids:
        titles = dict(
            (await db.execute(select(StudioProject.id, StudioProject.title).where(StudioProject.id.in_(pids)))).all()
        )
        for r in rows:
            if r["project_id"]:
                r["project_title"] = titles.get(r["project_id"])
    if project_id is not None:
        rows = [r for r in rows if r["project_id"] == project_id]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    if status:
        rows = [r for r in rows if r["status"] == status]

    def _ts(r: dict[str, Any]) -> float:
        t = r.get("created_at")
        if t is None:
            return 0.0
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        return t.timestamp()

    # 进行中 / 等待在前，其余按时间倒序
    rows.sort(key=lambda r: (r["status"] not in ("running", "waiting"), -_ts(r)))
    return {"items": rows[:limit], "counts": counts, "active": counts["running"] + counts["waiting"]}


async def summary(db: AsyncSession) -> dict[str, Any]:
    data = await list_tasks(db, days=2, limit=50)
    active = [r for r in data["items"] if r["status"] in ("running", "waiting")]
    return {"active": data["active"], "counts": data["counts"], "items": active[:20]}


async def retry(db: AsyncSession, key: str) -> dict[str, Any]:
    from app.services.flows import engine

    kind, _, ident = key.partition(":")
    if kind != "flow" or not ident.isdigit():
        raise engine.FlowError("这类任务不能在这里重试")
    run = await engine.continue_run(db, int(ident))
    return {"run_id": run.id}


async def stop(db: AsyncSession, key: str) -> dict[str, Any]:
    from app.services.flows import engine

    kind, _, ident = key.partition(":")
    if kind != "flow" or not ident.isdigit():
        raise engine.FlowError("这类任务不能在这里停止")
    run = await engine.stop_run(db, int(ident))
    return {"run_id": run.id, "status": run.status}
