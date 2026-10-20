from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.exceptions import AppException, NotFoundError
from app.models.content import ContentItem
from app.models.favorite import FavoriteItem, FavoriteTargetType
from app.models.studio import StudioArtifact, StudioProject
from app.repositories.content_repo import ContentRepo
from app.repositories.favorite_repo import FavoriteRepo
from app.repositories.studio_repo import StudioRepo
from app.schemas.favorite import FavoriteCreate
from app.schemas.studio import (
    CreateProject,
    GenerateDraft,
    StudioBrief,
    StudioDraft,
)
from app.services.favorite_cache import invalidate_favorite_cache
from app.services.llm.provider import call_llm_json_with_metadata
from app.services.studio_catalog import (
    catalog_for_user,
    clean_draft,
    compile_draft,
    production_prompt,
    resolve,
)
from app.services.studio_media import (
    MEDIA_ROOT,
)

logger = logging.getLogger(__name__)
SAFE_NAME = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def artifact_preview_file(artifact: StudioArtifact) -> Path | None:
    if artifact.status != "done" or not artifact.relative_path:
        return None
    path = (MEDIA_ROOT / artifact.relative_path).resolve()
    if path.suffix.lower() == ".zip":
        path = path.with_suffix("") / "dist" / "preview.mp4"
    return path if path.is_relative_to(MEDIA_ROOT) and path.is_file() else None


def artifact_source_file(artifact: StudioArtifact) -> Path | None:
    preview = artifact_preview_file(artifact)
    if preview is None:
        return None
    archive = (
        preview.parent.parent.with_suffix(".zip")
        if artifact.kind == "remotion_video"
        else preview.parent.with_suffix(".zip")
    )
    return archive if archive.is_relative_to(MEDIA_ROOT) and archive.is_file() else None


def artifact_dict(artifact: StudioArtifact) -> dict:
    path = (MEDIA_ROOT / artifact.relative_path).resolve() if artifact.relative_path else None
    progress = artifact.progress or {}
    return {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "version": artifact.version,
        "kind": artifact.kind,
        "status": artifact.status,
        "progress": progress,
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        "download_path": f"/api/v1/renders/{artifact.id}/download" if path else None,
        "preview_path": f"/api/v1/renders/{artifact.id}/preview" if artifact_preview_file(artifact) else None,
        "source_path": f"/api/v1/renders/{artifact.id}/source" if artifact_source_file(artifact) else None,
        "storage_path": str(path) if path else None,
        "error": artifact.error,
    }


async def _progress(
    db: AsyncSession,
    artifact: StudioArtifact,
    stage: str,
    percent: int | None = None,
    details: dict | None = None,
) -> None:
    previous = artifact.progress or {}
    logs = list(previous.get("logs", []))
    if previous.get("stage") != stage:
        logs.append({"at": datetime.now(UTC).isoformat(), "stage": stage})
    progress = {
        "stage": stage,
        "percent": percent,
        "updated_at": datetime.now(UTC).isoformat(),
        "logs": logs,
    }
    if details:
        progress.update(details)
    artifact.progress = {
        **(previous if isinstance(previous, dict) else {}),
        **progress,
    }
    await db.commit()


def _project_files(workspace: Path):
    for root, directories, filenames in os.walk(workspace):
        directories[:] = [name for name in directories if name not in {"node_modules", ".bundle", ".git"}]
        for name in filenames:
            yield Path(root) / name


async def _save_work(db: AsyncSession, project: StudioProject, artifact: StudioArtifact) -> None:
    payload = artifact_dict(artifact)
    await FavoriteRepo(db, project.owner_id).upsert(
        FavoriteCreate(
            target_type=FavoriteTargetType.WORK,
            target_key=f"studio:artifact:{artifact.id}",
            title=f"{project.title} · 版本 {artifact.version}",
            url=payload["preview_path"] or payload["download_path"],
            source_name="创意工作台",
            snapshot={
                "project_id": project.id,
                "artifact_id": artifact.id,
                "preview_url": payload["preview_path"],
                "download_url": payload["download_path"],
                "storage_path": payload["storage_path"],
                "kind": artifact.kind,
            },
        )
    )
    await db.commit()
    invalidate_favorite_cache()


def _source_snapshot(content: ContentItem | None, favorite: FavoriteItem | None, brief: StudioBrief) -> dict:
    if favorite:
        return {
            "kind": "favorite",
            "favorite_id": favorite.id,
            "target_type": str(getattr(favorite.target_type, "value", favorite.target_type)),
            "target_key": favorite.target_key,
            "title": favorite.title,
            "url": favorite.url,
            "source_name": favorite.source_name,
            "cover_url": favorite.cover_url,
            "snapshot": favorite.snapshot,
        }
    if not content:
        return {"kind": "manual", "title": brief.theme}
    return {
        "kind": "content",
        "content_id": content.id,
        "title": content.title,
        "url": content.url,
        "source_name": content.source_name,
        "published_at": content.published_at.isoformat() if content.published_at else None,
        "crawled_at": content.crawled_at.isoformat() if content.crawled_at else None,
        "summary": content.summary,
    }


def _seconds(value, fallback: float = 0.0) -> float:
    """Accept model-friendly timestamps such as ``0:00-0:05`` safely."""
    if isinstance(value, int | float):
        return max(0.0, float(value))
    text = str(value or "").strip()
    if not text:
        return fallback
    first = text.split("-", 1)[0].strip()
    try:
        if ":" in first:
            parts = [float(part) for part in first.split(":")]
            total = 0.0
            for part in parts:
                total = total * 60 + part
            return max(0.0, total)
        return max(0.0, float(first.rstrip("s秒")))
    except (TypeError, ValueError):
        return fallback


def _coerce_ai_draft(candidate: dict, brief: StudioBrief, previous: StudioDraft) -> StudioDraft:
    """Normalize common model variants into the bounded StudioDraft contract."""
    raw_shots = candidate.get("shots") or candidate.get("storyboard") or candidate.get("scenes") or []
    shots: list[dict] = []
    for index, raw in enumerate(raw_shots[:80]):
        item = raw if isinstance(raw, dict) else {"visual": str(raw)}
        shots.append(
            {
                "seconds": min(600.0, max(0.1, _seconds(item.get("seconds") or item.get("duration"), 3.0))),
                "beat": str(item.get("beat") or item.get("purpose") or f"镜头 {index + 1}"),
                "visual": str(item.get("visual") or item.get("scene") or item.get("description") or ""),
                "camera": str(item.get("camera") or item.get("shot") or item.get("movement") or ""),
                "audio": str(item.get("audio") or item.get("sound") or item.get("music") or ""),
                "transition": str(item.get("transition") or "直切"),
                "caption": str(item.get("caption") or item.get("subtitle") or ""),
                "prompt": str(item.get("prompt") or item.get("video_prompt") or item.get("generation_prompt") or ""),
            }
        )
    if brief.mode == "article":
        shots = []
    raw_cues = candidate.get("cues") or candidate.get("lyrics") or candidate.get("subtitles") or []
    cues: list[dict] = []
    for raw in raw_cues[:1500]:
        item = raw if isinstance(raw, dict) else {"text": str(raw)}
        text = str(item.get("text") or item.get("line") or item.get("caption") or "").strip()
        if text:
            cues.append({"time": min(600.0, _seconds(item.get("time") or item.get("start"), 0.0)), "text": text})
    body = str(
        candidate.get("body") or candidate.get("script") or candidate.get("narration") or candidate.get("text") or ""
    )
    normalized = {
        "title": str(candidate.get("title") or brief.theme),
        "logline": str(candidate.get("logline") or candidate.get("summary") or brief.intent),
        "body": body,
        "shots": shots,
        "cues": (cues or _dump(previous).get("cues", [])) if brief.mode == "music_video" else [],
        "provenance": "ai",
    }
    draft = clean_draft(StudioDraft.model_validate(normalized))
    if not draft.body:
        raise ValueError("AI 输出缺少正文或脚本")
    if brief.mode != "article" and not draft.shots:
        raise ValueError("AI 输出缺少分镜")
    return draft


def _retime_draft(draft: StudioDraft, duration: float) -> StudioDraft:
    """Keep shot boundaries truthful when the audio becomes the timeline clock.

    When LRC cues exist, use lyric starts as section boundaries where possible;
    otherwise preserve the draft's section count and distribute the audio
    duration evenly. This guarantees total coverage without claiming beat-level
    alignment that has not been analyzed.
    """
    if not draft.shots:
        return draft
    total = max(5.0, float(duration))
    boundaries = [0.0]
    cue_times = sorted({cue.time for cue in draft.cues if 0 < cue.time < total})
    if cue_times and len(cue_times) >= len(draft.shots) - 1:
        step = len(cue_times) / len(draft.shots)
        boundaries.extend(
            cue_times[max(0, min(len(cue_times) - 1, round(step * index) - 1))] for index in range(1, len(draft.shots))
        )
        boundaries = sorted(set(boundaries))
    if len(boundaries) != len(draft.shots):
        each = round(total / len(draft.shots), 3)
        boundaries = [round(each * index, 3) for index in range(len(draft.shots))]
    boundaries.append(total)
    shots = [
        shot.model_copy(update={"seconds": round(max(0.1, boundaries[index + 1] - boundaries[index]), 3)})
        for index, shot in enumerate(draft.shots)
    ]
    correction = round(total - sum(shot.seconds for shot in shots), 3)
    shots[-1] = shots[-1].model_copy(update={"seconds": round(max(0.1, shots[-1].seconds + correction), 3)})
    return draft.model_copy(update={"shots": shots})


def _project_dict(project: StudioProject, revisions: list, assets: list, artifacts: list) -> dict:
    brief = StudioBrief.model_validate(project.spec.get("brief", {}))
    draft = StudioDraft.model_validate(project.spec.get("draft", {}))
    if draft.provenance in {"ai", "compiled"}:
        draft = clean_draft(draft)
    previous_revision = None
    for revision in revisions:
        if revision.version >= project.version:
            continue
        previous = StudioDraft.model_validate(revision.spec.get("draft", {}))
        if previous.provenance in {"ai", "compiled"}:
            previous = clean_draft(previous)
        if (previous.body or previous.shots) and previous.model_dump(exclude={"provenance"}) != draft.model_dump(
            exclude={"provenance"}
        ):
            previous_revision = {"version": revision.version, "draft": _dump(previous)}
            break
    return {
        "id": project.id,
        "title": project.title,
        "version": project.version,
        "brief": _dump(brief),
        "draft": _dump(draft),
        "previous_revision": previous_revision,
        "source": project.source_snapshot,
        "finalized_version": project.finalized_version,
        "revisions": [
            {"version": item.version, "reason": item.reason, "created_at": item.created_at.isoformat()}
            for item in revisions
        ],
        "assets": [
            {
                "id": item.id,
                "kind": item.kind,
                "name": item.name,
                "duration": item.duration,
                "created_at": item.created_at.isoformat(),
            }
            for item in assets
        ],
        "artifacts": [artifact_dict(item) for item in artifacts],
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


async def get_project(db: AsyncSession, project_id: int, owner_id: int) -> StudioProject:
    project = await StudioRepo(db).get(project_id, owner_id)
    if not project:
        raise NotFoundError("创作工程", project_id)
    return project


async def project_view(db: AsyncSession, project_id: int, owner_id: int) -> dict:
    repo = StudioRepo(db)
    project = await get_project(db, project_id, owner_id)
    return _project_dict(
        project, await repo.revisions(project.id), await repo.assets(project.id), await repo.artifacts(project.id)
    )


async def create_project(db: AsyncSession, owner_id: int, request: CreateProject) -> dict:
    user_catalog = await catalog_for_user(db, owner_id)
    template, style = resolve(request.brief, templates=user_catalog["templates"], styles=user_catalog["styles"])
    content = await ContentRepo(db).get_by_id(request.content_id) if request.content_id else None
    favorite = await FavoriteRepo(db, owner_id).get_by_id(request.favorite_id) if request.favorite_id else None
    if request.content_id and not content:
        raise NotFoundError("内容", request.content_id)
    if request.favorite_id and not favorite:
        raise NotFoundError("收藏", request.favorite_id)
    initial = StudioDraft(title=request.brief.theme)
    spec = {"brief": _dump(request.brief), "draft": _dump(initial), "template": template, "style": style}
    project = await StudioRepo(db).create(owner_id, spec, _source_snapshot(content, favorite, request.brief))
    await db.commit()
    return await project_view(db, project.id, owner_id)


async def generate_project_draft(db: AsyncSession, owner_id: int, project_id: int, request: GenerateDraft) -> dict:
    repo = StudioRepo(db)
    project = await repo.get(project_id, owner_id, lock=True)
    if not project:
        raise NotFoundError("创作工程", project_id)
    if project.version != request.expected_version:
        raise AppException("工程已有新版本，请刷新后再生成", 409, {"current_version": project.version})
    brief = StudioBrief.model_validate(project.spec.get("brief", {}))
    previous = clean_draft(StudioDraft.model_validate(project.spec.get("draft", {})))
    audio = next((item for item in await repo.assets(project.id) if item.kind == "audio"), None)
    if brief.mode == "music_video" and audio and audio.duration:
        brief = brief.model_copy(update={"duration_seconds": audio.duration})
    if request.engine == "ai":
        try:
            mode_direction = {
                "article": (
                    "这是文章成稿。body 必须是完整、可直接编辑的文章正文，包含标题、开头、分段论述、例子和结尾。"
                    "文章以文字叙述、事实、例子和观点组织内容；shots 与 cues 为 []。"
                ),
                "music_video": (
                    "这是音乐 MV。body 写歌曲的视觉概念、段落情绪、意象和节奏方案；"
                    "shots 按前奏、主歌、副歌、桥段、尾奏组织，服务音乐和歌词时间轴。"
                ),
                "video_prompt": ("这是普通视频。body 写旁白或脚本，shots 写画面、镜头、声音和剪辑。"),
                "animation_video": (
                    "这是动画讲解视频，你是科普作者与动画分镜设计师。body 写可以直接朗读的完整中文旁白。"
                    "shots 用图形、图表、人物插画、标注、数字和关系变化解释来源中的概念与因果。"
                    "每个 audio 写对应的具体旁白，visual 写物体和图形，camera 写构图和元素运动，"
                    "prompt 写 Canvas/Three.js/CSS 可以制作的具体动画。全部场景服务于讲清这个选题。"
                ),
            }[brief.mode]
            presentation_direction = {
                "kinetic": "使用动态图形、数据图表、文字排版、箭头与强调动画呈现内容。",
                "ascii": "使用字符网格构造对象、关系图与逐步变化的 ASCII 动画。",
                "tui": "使用终端窗口、面板、表格、状态变化与数据流构建 TUI 动画。",
                "cinematic": "以主体动作、空间关系和镜头构图组织场景。",
            }.get(brief.presentation, "")
            requirements = [
                "优先按照 creator_direction 和 revision_instructions 的叙事顺序、内容取舍与表达方式成稿",
                "action 为 refine 时以 previous_draft 为底稿，按要求修改并保留其余内容；generate 时按当前设定提供全新完整方案",
                "body 是完整正文、可直接朗读的旁白或 MV 视觉方案字符串",
                "模板和风格作为可选参考，留空时采用自由结构",
            ]
            if brief.mode != "article":
                requirements += [
                    "为每个镜头填写具体画面、元素运动、声音、衔接、字幕和生成提示词",
                    f"分镜总时长为 {brief.duration_seconds:g} 秒",
                    "字幕按 brief.bilingual 的设置输出",
                    presentation_direction,
                ]
            if brief.mode == "music_video":
                requirements.append("cues 直接沿用 lyric_timeline，镜头时间随音频时间轴安排")
            payload, _metadata = await call_llm_json_with_metadata(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是内容编导、脚本作者和视频方案设计师。"
                            "返回一个 JSON 对象。"
                            "JSON 必须包含 title、logline、body、shots、cues。"
                            "shots 每项包含 seconds、beat、visual、camera、audio、transition、caption、prompt。"
                            + mode_direction
                            + " "
                            "把用户的创作思路作为首要依据，来源作为背景资料。"
                            "每个输出字段直接写创作内容与制作方案。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "brief": _dump(brief),
                                "content_template": project.spec.get("template"),
                                "visual_style": project.spec.get("style"),
                                "content_form": brief.mode,
                                "presentation": brief.presentation,
                                "production_path": brief.production,
                                "source": project.source_snapshot,
                                "request_version": project.version,
                                "previous_draft": _dump(previous) if request.action == "refine" else {},
                                "lyric_timeline": _dump(previous)["cues"] if brief.mode == "music_video" else [],
                                "action": request.action,
                                "creator_direction": brief.intent,
                                "revision_instructions": request.instructions,
                                "requirements": requirements,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=brief.intent and 0.45 or 0.35,
                max_tokens=12000,
                scene="studio_draft",
                routing_group="default",
            )
            if not isinstance(payload, dict):
                raise ValueError("模型返回的成稿不是 JSON 对象")
            candidate = payload.get("draft") if isinstance(payload.get("draft"), dict) else payload
            draft = _coerce_ai_draft(candidate, brief, previous)
            if brief.mode == "music_video" and previous.cues:
                # LRC is the source of truth for lyrics timing. The model may
                # suggest visual sections, but it must not rewrite lyric cues.
                draft = draft.model_copy(update={"cues": previous.cues})
            if brief.mode == "music_video" and audio and audio.duration:
                draft = _retime_draft(draft, audio.duration)
        except Exception as exc:
            logger.warning("Studio AI draft failed: %s", str(exc)[:240])
            message = str(exc) if isinstance(exc, ValueError) else "AI 成稿失败，请检查模型配置或稍后重试"
            raise AppException(message, 503) from exc
    else:
        draft = compile_draft(brief, previous, project.spec.get("template"))
        if brief.mode == "music_video" and audio and audio.duration:
            draft = _retime_draft(draft, audio.duration)
    project.version += 1
    project.spec = {**project.spec, "brief": _dump(brief), "draft": _dump(draft)}
    project.finalized_version = None
    await repo.snapshot(
        project, "refined" if request.action == "refine" else "ai" if request.engine == "ai" else "compiled"
    )
    await db.commit()
    return await project_view(db, project.id, owner_id)


def _write_animation_contract(workspace: Path, project: StudioProject, brief: StudioBrief, draft: StudioDraft) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    # The worker receives only the frozen creative spec. It never receives
    # model keys, backend env files, or arbitrary source paths.
    contract = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "project": {
            "id": project.id,
            "title": project.title,
            "version": project.version,
            "brief": _dump(brief),
            "draft": _dump(clean_draft(draft)),
            "content_template": project.spec.get("template"),
            "visual_style": project.spec.get("style"),
            "production_prompt": production_prompt(
                brief,
                draft,
                project.source_snapshot,
                template_override=project.spec.get("template"),
                style_override=project.spec.get("style"),
            ),
            "source": {
                "title": project.source_snapshot.get("title"),
                "url": project.source_snapshot.get("url"),
                "source_name": project.source_snapshot.get("source_name"),
            },
        },
        "delivery": {
            "entrypoint": "render.ps1",
            "expected_outputs": ["src/Scenes.tsx", "design.ready.json"],
            "rendered_outputs": ["dist/preview.mp4", "dist/timeline.json"],
            "deterministic": True,
            "network": False,
        },
    }
    (workspace / "production_spec.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (workspace / "README.md").write_text(
        "# Creative Workbench production workspace\n\n"
        "Read production_spec.json and timeline.json. Design src/Scenes.tsx using the "
        "local components and assets. Keep Chinese text in the layout layer. "
        "When source design is complete, write design.ready.json and return. "
        "The workbench controller compiles the source, checks the frames and renders the video.\n",
        encoding="utf-8",
    )


async def recover_unfinished_artifacts() -> int:
    """Close jobs left in-flight by a previous process lifetime.

    Studio workers are intentionally local background tasks. If the API process
    exits while one is running, there is no durable worker lease to resume it.
    Marking it as retryable keeps the UI truthful instead of leaving a
    permanent spinner.
    """
    async with async_session() as db:
        artifacts = await StudioRepo(db).unfinished()
        for artifact in artifacts:
            artifact.status = "error"
            artifact.error = "上次服务进程中断，未生成可播放预览；请重试"
            artifact.progress = {**(artifact.progress or {}), "stage": "任务中断"}
        if artifacts:
            await db.commit()
        return len(artifacts)


async def build_prompt(db: AsyncSession, owner_id: int, project_id: int) -> dict:
    project = await get_project(db, project_id, owner_id)
    brief = StudioBrief.model_validate(project.spec.get("brief", {}))
    draft = StudioDraft.model_validate(project.spec.get("draft", {}))
    return {
        "project_id": project.id,
        "version": project.version,
        "prompt": production_prompt(
            brief,
            draft,
            project.source_snapshot,
            template_override=project.spec.get("template"),
            style_override=project.spec.get("style"),
        ),
    }
