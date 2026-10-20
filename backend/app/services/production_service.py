"""讲解视频 / MV 制作（创作工作台设计 6.2、12）：包装现有 studio_remotion / studio_media / studio_subtitles，
读取「定稿文案 + 产出物 settings」，由成片流程（分镜 → 美术 → 制作 → 质检）的制作、质检角色调用。

* ``start_render``：检查定稿与前置条件，启动 video_production 流程，执行者取产出物 settings.executor。
* 制作者（``PRODUCERS``，按执行者）：建一条 ProjectArtifact（挂产出物、带 settings 快照），写工作目录与合同，
  配音 → 设计 → 编译检查 → 渲染 → 整理；阶段写进 artifact.progress，同时推到运行事件。
  质检退回时把问题写进工作目录 ``qa_feedback.json``，执行者在已有源码上修改。
  上一次同版本的制作已交付设计源码（design.ready.json）时复用源码；没有质检意见时跳过设计直接渲染。
* 质检（``inspect``）：时长、字幕对齐、黑帧、静音、与分镜不符的镜头。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import zipfile
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ValidationError
from app.models.agent_run import AgentRun
from app.models.project import Project, ProjectArtifact, ProjectOutput, ProjectUpload
from app.schemas.studio import StudioDraft
from app.services import project_service as ps, run_events

logger = logging.getLogger(__name__)

PRODUCTION_KINDS = {"video", "mv"}
ACTIVE_RUN = {"queued", "running", "waiting", "paused"}
FRAME_TOLERANCE = 0.1  # 时长允许 10%（至少 2 秒）偏差


def media_root() -> Path:
    from app.services.studio_media import MEDIA_ROOT

    return MEDIA_ROOT


# ── 启动 ──


async def _audio_asset(db: AsyncSession, project_id: int) -> ProjectUpload | None:
    return (
        await db.execute(
            select(ProjectUpload)
            .where(ProjectUpload.project_id == project_id, ProjectUpload.kind == "audio")
            .order_by(ProjectUpload.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def default_preflight(db: AsyncSession, project: Project, output: ProjectOutput) -> list[str]:
    """真实制作的前置条件；返回缺什么（测试里替换）。"""
    from app.services.studio_tts import tts_config

    settings = output.settings or {}
    problems = []
    if output.kind == "mv" and not await _audio_asset(db, project.id):
        problems.append("制作 MV 前需要上传音频")
    if output.kind == "video" and not (await tts_config(db))["configured"]:
        problems.append("讲解视频需要配音：请在设置 · AI 模型与配音里配置千问 TTS")
    executor = settings.get("executor") or "deepseek_harness"
    if output.kind == "video" or settings.get("production") == "code_animation":
        from app.services import agent_adapters

        missing = agent_adapters.missing(executor)
        if missing:
            problems.append(missing)
    return problems


PREFLIGHT: Callable[[AsyncSession, Project, ProjectOutput], Awaitable[list[str]]] = default_preflight


async def start_render(db: AsyncSession, output_id: int) -> dict:
    from app.services.flows import engine

    output = await ps.get_output(db, output_id)
    if output.kind not in PRODUCTION_KINDS:
        raise ValidationError("这个产出物不需要制作")
    project = await ps.get_project(db, output.project_id)
    if not project.finalized_version:
        raise ps.conflict("not_finalized", "定稿后可制作")
    current = (output.content or {}).get("run_id")
    if current:
        prev = await db.get(AgentRun, current)
        if prev and prev.status in ACTIVE_RUN:
            raise ps.conflict("render_running", "正在制作，可以在任务里查看或停止", run_id=prev.id)
    problems = await PREFLIGHT(db, project, output)
    if problems:
        raise AppException("；".join(problems), 503, {"code": "production_not_ready", "problems": problems})
    settings = output.settings or {}
    executor = settings.get("executor") or "deepseek_harness"
    topic = ps.copy_brief((project.spec or {}).get("brief")).get("theme") or project.title
    try:
        run = await engine.start_run(
            db,
            "video_production",
            {"project_id": str(project.id), "output_id": str(output.id), "topic": topic},
            title=f"{output.title or ps.OUTPUT_TITLES.get(output.kind, '成片')} · {topic}"[:300],
            project_id=project.id,
            trigger="project",
            launch=False,
        )
    except engine.FlowError as exc:
        raise AppException(str(exc), 503, {"code": "model_unavailable"}) from exc
    inputs = dict(run.inputs or {})
    inputs["_executors"] = {"produce": executor}
    run.inputs = inputs
    output.content = {**(output.content or {}), "run_id": run.id}
    output.status = "rendering"
    output.based_on_version = project.finalized_version
    await db.commit()
    engine._launch(run.id, {"run_id": run.id, "inputs": inputs, "outputs": {}, "decisions": {}})
    return {"run_id": run.id, "output": await ps.output_view(db, output.id)}


async def on_run_finished(db: AsyncSession, run: AgentRun) -> None:
    oid = (run.inputs or {}).get("output_id")
    if not str(oid or "").isdigit():
        return
    output = await db.get(ProjectOutput, int(oid), populate_existing=True)
    if output is None or (output.content or {}).get("run_id") != run.id:
        return
    if run.status == "done":
        output.status = "done"
        art_id = (output.content or {}).get("artifact_id")
        art = await db.get(ProjectArtifact, art_id) if art_id else None
        project = await db.get(Project, output.project_id)
        if art and project and SAVE_WORK:
            from app.services.studio_service import _save_work

            await _save_work(db, project, art)
    elif run.status == "failed":
        output.status = "failed"
    elif run.status == "stopped":
        output.status = "draft"
    output.content = {**(output.content or {}), "run_status": run.status, "run_reason": run.status_reason}
    await db.commit()
    if run.status == "done":
        from app.services.project_service import _feishu_stage

        await _feishu_stage(db, output.project_id)


SAVE_WORK = True  # 测试里关掉（写收藏夹走旧缓存）


# ── 制作 ──


@dataclass
class ProductionJob:
    db: AsyncSession
    project: Project
    output: ProjectOutput
    version: int
    brief: Any  # StudioBrief（文案层 + 制作层）
    draft: StudioDraft  # 定稿文案，分镜换成分镜角色细化后的版本
    style: dict | None
    executor: str
    keyframes: list[dict[str, Any]]
    feedback: list[dict[str, Any]]
    artifact: ProjectArtifact
    workspace: Path
    run_id: int | None = None
    step_id: int | None = None
    reuse_from: Path | None = None
    stages: list[dict[str, Any]] = field(default_factory=list)

    async def stage(self, name: str, percent: int | None = None) -> None:
        from app.services.studio_service import _progress

        now = datetime.now(UTC)
        if not self.stages or self.stages[-1]["stage"] != name:
            self.stages.append({"stage": name, "at": now.isoformat()})
        started = self.stages[0]["at"]
        elapsed = int((now - datetime.fromisoformat(started)).total_seconds())
        await _progress(self.db, self.artifact, name, percent, {"elapsed_seconds": elapsed, "executor": self.executor})
        if self.run_id:
            await run_events.publish(
                self.run_id,
                {
                    "type": "stage",
                    "step_id": self.step_id,
                    "artifact_id": self.artifact.id,
                    "stage": name,
                    "percent": percent,
                    "elapsed_seconds": elapsed,
                },
            )


@dataclass
class ProductionResult:
    video: Path
    duration: float | None = None
    timeline: dict[str, Any] | None = None
    reused_design: bool = False


def workspace_for(project_id: int, artifact_id: int) -> Path:
    return media_root() / str(project_id) / f"harness-{artifact_id}"


def _previous_design(job: ProductionJob, prev: ProjectArtifact | None) -> Path | None:
    if prev is None:
        return None
    ws = workspace_for(job.project.id, prev.id)
    if (ws / "design.ready.json").is_file() and (ws / "src" / "Scenes.tsx").is_file():
        return ws
    return None


def _write_feedback(job: ProductionJob) -> None:
    if not job.feedback:
        (job.workspace / "qa_feedback.json").unlink(missing_ok=True)
        return
    (job.workspace / "qa_feedback.json").write_text(
        json.dumps({"round": len(job.feedback), "issues": job.feedback}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _keyframe_note(job: ProductionJob) -> None:
    if job.keyframes:
        (job.workspace / "keyframes.json").write_text(
            json.dumps(job.keyframes, ensure_ascii=False, indent=2), encoding="utf-8"
        )


async def harness_producer(job: ProductionJob) -> ProductionResult:
    """代码动画：工作目录 + 合同 → 配音 / 时间轴 → 执行者设计 Scenes.tsx → 字幕层 → Remotion 渲染 → 工程 ZIP。"""
    from app.services import agent_adapters
    from app.services.studio_media import _render_style
    from app.services.studio_remotion import prepare_animation, render_animation
    from app.services.studio_service import _project_files, _write_animation_contract
    from app.services.studio_subtitles import install_subtitle_layer

    ws = job.workspace
    project = job.project
    # 合同读 project.spec / version：用定稿版本的内容，不改库里的项目
    frozen = Project(
        id=project.id, title=project.title, version=job.version, spec={**(project.spec or {}), "style": job.style}
    )
    frozen.source_snapshot = project.source_snapshot or {}
    _write_animation_contract(ws, frozen, job.brief, job.draft)
    reuse = False
    if job.reuse_from is not None:
        shutil.copytree(job.reuse_from / "src", ws / "src", dirs_exist_ok=True)
        if (job.reuse_from / "public").is_dir():
            shutil.copytree(job.reuse_from / "public", ws / "public", dirs_exist_ok=True)
        reuse = not job.feedback
    _write_feedback(job)
    _keyframe_note(job)

    async def on_stage(stage: str, percent=None):
        await job.stage(stage, percent)

    soundtrack = None
    if job.brief.mode == "music_video":
        audio = await _audio_asset(job.db, project.id)
        if not audio:
            raise ValidationError("请上传歌曲音频")
        soundtrack = media_root() / audio.relative_path
    # 有可复用的源码时保留 Scenes.tsx（质检退回时执行者在它上面改）
    timeline = await prepare_animation(
        job.db,
        ws,
        job.brief,
        job.draft,
        _render_style(job.brief, job.style),
        on_stage,
        soundtrack,
        reuse_design=job.reuse_from is not None,
    )
    if reuse:
        await job.stage("复用设计源码")
    else:
        await agent_adapters.design(job.executor, ws, on_stage, job=job)
    await job.stage("生成旁白字幕")
    install_subtitle_layer(ws, timeline, required=job.brief.mode == "animation_video")
    await job.stage("Remotion 渲染")
    video = await render_animation(ws, on_stage)
    await job.stage("整理工程产物", 99)
    archive = ws.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in _project_files(ws):
            bundle.write(path, path.relative_to(ws))
    return ProductionResult(video=video, timeline=timeline, reused_design=reuse)


async def native_mv_producer(job: ProductionJob) -> ProductionResult:
    from app.services.studio_media import render_native_mv

    audio = await _audio_asset(job.db, job.project.id)
    if not audio:
        raise ValidationError("请上传歌曲音频")
    brief = job.brief.model_copy(update={"duration_seconds": audio.duration or job.brief.duration_seconds})

    async def on_progress(percent: int):
        await job.stage("合成渲染", percent)

    video = await render_native_mv(
        brief,
        job.draft,
        media_root() / audio.relative_path,
        job.workspace,
        style_override=job.style,
        on_progress=on_progress,
    )
    return ProductionResult(video=video, duration=audio.duration)


def pick_producer(output: ProjectOutput) -> Callable[[ProductionJob], Awaitable[ProductionResult]]:
    settings = output.settings or {}
    if output.kind == "mv" and (settings.get("production") or "native_mv") == "native_mv":
        return PRODUCERS["native_mv"]
    return PRODUCERS["code_animation"]


PRODUCERS: dict[str, Callable[[ProductionJob], Awaitable[ProductionResult]]] = {
    "code_animation": harness_producer,
    "native_mv": native_mv_producer,
}


async def resolve_style(db: AsyncSession, project: Project, brief: dict, settings: dict) -> dict | None:
    if not settings.get("style_id"):
        return None
    from app.services.studio_catalog import catalog_for_user, resolve

    catalog = await catalog_for_user(db, project.owner_id)
    _t, style = resolve(ps.studio_brief(brief, settings), templates=catalog["templates"], styles=catalog["styles"])
    return style


async def produce(
    db: AsyncSession,
    *,
    output_id: int,
    shots: list[dict[str, Any]],
    keyframes: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    executor: str,
    run_id: int | None = None,
    step_id: int | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    """制作一版成片：读定稿文案 + 产出物 settings，结果写成 ProjectArtifact（output_id、settings 快照）。"""
    output = await ps.get_output(db, output_id)
    project = await ps.get_project(db, output.project_id)
    version = output.based_on_version or project.finalized_version
    if not version:
        raise ValidationError("定稿后可制作")
    spec = deepcopy((await ps._revision(db, project.id, version)).spec)
    brief_raw = ps.copy_brief(spec.get("brief"))
    settings = dict(output.settings or {})
    if output.kind == "mv":
        brief_raw["mode"] = "music_video"
    elif brief_raw.get("mode") not in ("animation_video", "video_prompt"):
        brief_raw["mode"] = "animation_video"
    brief = ps.studio_brief(brief_raw, settings)
    draft_raw = dict(spec.get("draft") or {})
    if shots:
        draft_raw["shots"] = shots
    from app.services.studio_catalog import clean_draft

    draft = clean_draft(StudioDraft.model_validate(draft_raw))
    style = await resolve_style(db, project, brief_raw, settings)
    prev = (
        await db.execute(
            select(ProjectArtifact)
            .where(ProjectArtifact.output_id == output.id, ProjectArtifact.version == version)
            .order_by(ProjectArtifact.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    kind = "native_mv" if pick_producer(output) is PRODUCERS["native_mv"] else "remotion_video"
    artifact = ProjectArtifact(
        project_id=project.id,
        version=version,
        kind=kind,
        status="rendering",
        output_id=output.id,
        settings={**settings, "executor": executor, "run_id": run_id, "attempt": attempt},
        progress={},
    )
    db.add(artifact)
    await db.commit()
    ws = (
        workspace_for(project.id, artifact.id)
        if kind == "remotion_video"
        else (media_root() / str(project.id) / f"artifact-{artifact.id}")
    )
    ws.mkdir(parents=True, exist_ok=True)
    job = ProductionJob(
        db=db,
        project=project,
        output=output,
        version=version,
        brief=brief,
        draft=draft,
        style=style,
        executor=executor,
        keyframes=keyframes,
        feedback=feedback,
        artifact=artifact,
        workspace=ws,
        run_id=run_id,
        step_id=step_id,
    )
    job.reuse_from = _previous_design(job, prev) if kind == "remotion_video" else None
    output.content = {**(output.content or {}), "artifact_id": artifact.id}
    await db.commit()
    await job.stage("准备制作", 0)
    try:
        result = await pick_producer(output)(job)
    except asyncio.CancelledError:
        artifact.status, artifact.error = "error", "运行被停止"
        await job.stage("已停止")
        raise
    except Exception as exc:
        import subprocess

        if isinstance(exc, subprocess.TimeoutExpired):
            msg = f"{executor} 设计超过 10 分钟，已停止。可重试，已生成的源码会复用"
        else:
            msg = (
                str(exc)[:400]
                if isinstance(exc, AppException | ValueError | RuntimeError)
                else "制作失败，请查看工作目录日志"
            )
        artifact.status, artifact.error = "error", msg
        await job.stage("制作失败")
        raise ValidationError(msg) from exc
    artifact.status = "done"
    artifact.relative_path = str(result.video.relative_to(media_root()))
    await job.stage("制作完成", 100)
    return {
        "studio_artifact_id": artifact.id,
        "relative_path": artifact.relative_path,
        "workspace": str(ws.relative_to(media_root())),
        "version": version,
        "kind": output.kind,
        "executor": executor,
        "reused_design": result.reused_design,
        "duration": result.duration,
        "stages": job.stages,
        "attempt": attempt,
    }


# ── 质检 ──


@dataclass
class Probe:
    duration: float | None
    black: list[tuple[float, float]] = field(default_factory=list)
    silence: list[tuple[float, float]] = field(default_factory=list)
    available: bool = True


async def ffmpeg_probe(video: Path, *, detect_silence: bool) -> Probe:
    from app.services.studio_media import run_process, tool

    try:
        ffprobe, ffmpeg = tool("ffprobe"), tool("ffmpeg")
    except Exception:  # noqa: BLE001
        return Probe(duration=None, available=False)
    meta = json.loads(
        await run_process([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)])
    )
    duration = float(meta["format"]["duration"])
    filters = ["blackdetect=d=1.0:pix_th=0.10"]
    args = [ffmpeg, "-hide_banner", "-nostdin", "-i", str(video), "-vf", ",".join(filters)]
    args += ["-af", "silencedetect=noise=-50dB:d=2"] if detect_silence else ["-an"]
    args += ["-f", "null", "-"]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _out, err = await asyncio.wait_for(proc.communicate(), timeout=max(120, duration * 3))
    text = err.decode("utf-8", errors="replace")
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", text)]
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", text)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", text)]
    silence = [(s, ends[i] if i < len(ends) else duration) for i, s in enumerate(starts)]
    return Probe(duration=duration, black=black, silence=silence)


PROBE: Callable[..., Awaitable[Probe]] = ffmpeg_probe


def _shot_at(shots: list[dict[str, Any]], t: float) -> int:
    acc = 0.0
    for i, s in enumerate(shots, 1):
        acc += float(s.get("seconds") or 0)
        if t < acc:
            return i
    return len(shots)


def _ts(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def evaluate(
    *,
    kind: str,
    shots: list[dict[str, Any]],
    probe: Probe,
    timeline: dict[str, Any] | None,
    captions: list[dict] | None,
) -> dict[str, Any]:
    """质检规则（纯函数，便于测试）：返回 {passed, checks[], issues[]}。"""
    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    expected = sum(float(s.get("seconds") or 0) for s in shots)
    if timeline and timeline.get("scenes") and timeline.get("fps"):
        expected = sum(sc.get("frames", 0) for sc in timeline["scenes"]) / float(timeline["fps"])
    if not probe.available or probe.duration is None:
        checks.append({"key": "duration", "label": "时长", "ok": None, "detail": "未安装 ffmpeg，跳过画面检查"})
    else:
        tol = max(2.0, expected * FRAME_TOLERANCE)
        ok = expected <= 0 or abs(probe.duration - expected) <= tol
        checks.append(
            {
                "key": "duration",
                "label": "时长",
                "ok": ok,
                "detail": f"成片 {_ts(probe.duration)}，分镜 {_ts(expected)}",
            }
        )
        if not ok:
            issues.append(
                {"check": "duration", "problem": f"成片时长 {_ts(probe.duration)} 与分镜 {_ts(expected)} 不符"}
            )
        bad_black = [(a, b) for a, b in probe.black if b - a >= 1.0]
        checks.append(
            {
                "key": "black",
                "label": "黑帧",
                "ok": not bad_black,
                "detail": f"{len(bad_black)} 段" if bad_black else "无",
            }
        )
        for a, b in bad_black[:10]:
            issues.append(
                {"check": "black", "shot": _shot_at(shots, a), "problem": f"{_ts(a)}–{_ts(b)} 黑屏 {b - a:.1f} 秒"}
            )
        if kind == "video":
            long_silence = [(a, b) for a, b in probe.silence if b - a >= 3.0]
            checks.append(
                {
                    "key": "silence",
                    "label": "静音",
                    "ok": not long_silence,
                    "detail": f"{len(long_silence)} 段" if long_silence else "无",
                }
            )
            for a, b in long_silence[:10]:
                issues.append(
                    {
                        "check": "silence",
                        "shot": _shot_at(shots, a),
                        "problem": f"{_ts(a)}–{_ts(b)} 无声 {b - a:.1f} 秒",
                    }
                )
    if kind == "video":
        narration = "".join(str(s.get("audio") or "") for s in shots)
        cap_text = "".join(str(c.get("text") or "") for c in captions or [])
        squash = lambda x: re.sub(r"\s+", "", x)  # noqa: E731
        ok = bool(captions) and squash(cap_text) == squash(narration)
        if ok and probe.duration:
            ok = max(float(c.get("end") or 0) for c in captions or [{}]) <= probe.duration + 0.5
        checks.append(
            {
                "key": "subtitles",
                "label": "字幕对齐",
                "ok": ok,
                "detail": f"{len(captions or [])} 条" if ok else "字幕与旁白不一致或超出成片",
            }
        )
        if not ok:
            issues.append({"check": "subtitles", "problem": "字幕没有完整覆盖旁白，或时间超出成片"})
    if timeline is not None:
        scenes = timeline.get("scenes") or []
        mismatched = []
        for i, s in enumerate(shots, 1):
            sc = scenes[i - 1] if i - 1 < len(scenes) else None
            if sc is None or (sc.get("audio") or "") != (s.get("audio") or ""):
                mismatched.append(i)
        if len(scenes) > len(shots):
            mismatched += list(range(len(shots) + 1, len(scenes) + 1))
        checks.append(
            {
                "key": "storyboard",
                "label": "与分镜一致",
                "ok": not mismatched,
                "detail": f"镜 {', '.join(map(str, mismatched[:8]))} 不符" if mismatched else f"{len(shots)} 镜一致",
            }
        )
        for i in mismatched[:10]:
            issues.append({"check": "storyboard", "shot": i, "problem": f"第 {i} 镜与分镜不符"})
    for n, it in enumerate(issues, 1):
        it["id"] = f"q{n}"
    passed = all(c["ok"] is not False for c in checks)
    return {"passed": passed, "checks": checks, "issues": issues}


async def inspect(db: AsyncSession, produced: dict[str, Any], shots: list[dict[str, Any]]) -> dict[str, Any]:
    root = media_root()
    video = root / produced["relative_path"]
    ws = root / produced["workspace"]
    timeline = None
    captions = None
    tl = ws / "timeline.json"
    if tl.is_file():
        timeline = json.loads(tl.read_text(encoding="utf-8"))
        captions = timeline.get("captions")
        if captions is None:
            from app.services.studio_subtitles import caption_track

            try:
                captions = caption_track(timeline, ws)
            except Exception:  # noqa: BLE001
                captions = []
    probe = await PROBE(video, detect_silence=produced.get("kind") == "video")
    report = evaluate(
        kind=produced.get("kind") or "video", shots=shots, probe=probe, timeline=timeline, captions=captions
    )
    report["duration"] = probe.duration
    art = await db.get(ProjectArtifact, produced["studio_artifact_id"])
    if art is not None:
        art.progress = {**(art.progress or {}), "qa": {k: report[k] for k in ("passed", "checks", "issues")}}
        await db.commit()
    return report
