"""成片流程的角色（创作工作台设计 6.2）：分镜 → 美术 → 制作 → 质检（不通过退回制作，最多 2 次）。

* 分镜（storyboarder）：按定稿版本细化镜头（画面、镜头运动、旁白、字幕、生成提示词），每镜标出依据的文稿段落；
  定稿里的分镜已经完整时直接沿用、不调模型。
* 美术（artist）：给每个镜头出关键帧——项目素材里已指定的关键帧直接用；生成服务可用时生图，否则只给提示词。
* 制作（producer）：交给 ``production_service.produce``，执行者取运行输入（产出物 settings.executor）。
* 质检（qa）：``production_service.inspect``；不通过时产物 passed=False，引擎按 loop_to 退回制作。
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.schemas.studio import StudioShot
from app.services.flows.roles import ArtifactOut, RoleContext, RoleError, _llm


async def _ids(ctx: RoleContext) -> tuple[int, int]:
    pid, oid = ctx.inputs.get("project_id"), ctx.inputs.get("output_id")
    if not str(pid or "").isdigit() or not str(oid or "").isdigit():
        raise RoleError("成片流程需要项目和产出物")
    return int(pid), int(oid)


async def _frozen(ctx: RoleContext):
    from app.services import project_service as ps

    pid, oid = await _ids(ctx)
    output = await ps.get_output(ctx.db, oid)
    project = await ps.get_project(ctx.db, pid)
    version = output.based_on_version or project.finalized_version
    if not version:
        raise RoleError("定稿后可制作")
    spec = deepcopy((await ps._revision(ctx.db, pid, version)).spec)
    return project, output, version, spec


def _complete(shots: list[dict[str, Any]], kind: str) -> bool:
    if not shots:
        return False
    need = ("visual", "prompt") if kind == "mv" else ("visual", "audio", "prompt")
    return all(str(s.get(k) or "").strip() for s in shots for k in need)


def _match_paragraphs(shots: list[dict[str, Any]], paras: list[dict[str, Any]]) -> list[list[int]]:
    """沿用定稿分镜时，按旁白文字在段落里的出现找依据段落。"""
    out = []
    for s in shots:
        audio = "".join(str(s.get("audio") or "").split())
        hit = [i for i, p in enumerate(paras, 1) if audio and (audio[:12] in "".join(p["text"].split()))]
        out.append(hit[:3])
    return out


def _clean_shots(raw: Any, target: float | None) -> list[dict[str, Any]]:
    shots = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            shot = StudioShot.model_validate(
                {
                    "seconds": float(item.get("seconds") or 4),
                    **{
                        k: str(item.get(k) or "")[:lim]
                        for k, lim in (
                            ("beat", 500),
                            ("visual", 2000),
                            ("camera", 1000),
                            ("audio", 1000),
                            ("caption", 300),
                            ("prompt", 4000),
                        )
                    },
                    "transition": str(item.get("transition") or "直切")[:300],
                }
            )
        except Exception:  # noqa: BLE001
            continue
        shots.append({**shot.model_dump(mode="json"), "_paragraphs": item.get("paragraphs") or []})
        if len(shots) >= 80:
            break
    if target and shots:
        total = sum(s["seconds"] for s in shots)
        if total > 0 and abs(total - target) / target > 0.15:
            k = target / total
            for s in shots:
                s["seconds"] = round(max(0.5, min(600, s["seconds"] * k)), 2)
    return shots


async def storyboarder(ctx: RoleContext) -> list[ArtifactOut]:
    from app.services import project_lineage
    from app.services.project_service import copy_brief, paragraphs_with_ids

    project, output, version, spec = await _frozen(ctx)
    draft = spec.get("draft") or {}
    brief = copy_brief(spec.get("brief"))
    settings = output.settings or {}
    paras = paragraphs_with_ids(draft.get("body") or "")
    target = float(brief.get("duration_seconds") or 0) or None
    base_shots = draft.get("shots") or []
    version_art = await project_lineage.ensure_version_artifact(ctx.db, project, version)
    if _complete(base_shots, output.kind) and not ctx.override.get("prompt_extra"):
        shots = [dict(s) for s in base_shots]
        para_refs = _match_paragraphs(shots, paras)
        summary = f"沿用定稿 v{version} 的 {len(shots)} 个镜头"
    else:
        system = (
            "你是分镜师。把定稿文稿拆成镜头表，严格沿用定稿的事实与旁白，不新增事实。"
            "每个镜头写：seconds、beat（这一镜讲什么）、visual（具体画面元素）、camera（构图与元素运动）、"
            "audio（这一镜要朗读的旁白原文，所有镜头的 audio 连起来等于完整旁白）、transition、caption（画面强调字）、"
            "prompt（给生图 / 动画用的画面提示词）、paragraphs（依据的文稿段落序号）。"
            f"表现方案：{settings.get('presentation') or 'kinetic'}；画幅：{settings.get('aspect_ratio') or '16:9'}。"
            + (f"总时长约 {target:g} 秒。" if target else "")
            + '只输出 JSON：{"shots": [...], "summary": "一句话"}'
            + ctx.system_extra()
        )
        if output.kind == "mv":
            system += "这是音乐 MV：audio 留空，镜头按歌词时间轴（cues）安排，秒数之和等于歌曲时长。"
        user = {
            "标题": draft.get("title"),
            "梗概": draft.get("logline"),
            "文稿段落": [f"[{i}] {p['text']}" for i, p in enumerate(paras, 1)],
            "已有分镜": base_shots,
            "歌词时间轴": draft.get("cues") if output.kind == "mv" else None,
        }
        reply = await _llm(
            ctx,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"运行 #{ctx.run_id}\n" + json.dumps(user, ensure_ascii=False)},
            ],
            scene="flow_storyboarder",
            max_tokens=8000,
        )
        if not isinstance(reply, dict):
            raise RoleError("分镜没有返回 JSON 对象")
        shots = _clean_shots(reply.get("shots"), target)
        if not shots:
            raise RoleError("分镜没有给出可用的镜头")
        para_refs = []
        for s in shots:
            refs = []
            for r in s.pop("_paragraphs", []):
                if str(r).isdigit() and 1 <= int(r) <= len(paras) and int(r) not in refs:
                    refs.append(int(r))
            para_refs.append(refs)
        summary = str(reply.get("summary") or "").strip()[:200] or f"{len(shots)} 个镜头"
    for s in shots:
        s.pop("_paragraphs", None)
    links: list[dict[str, Any]] = [{"relation": "derived_from", "target_type": "artifact", "target_id": version_art.id}]
    for i, refs in enumerate(para_refs, 1):
        for r in refs:
            links.append(
                {
                    "relation": "derived_from",
                    "target_type": "artifact",
                    "target_id": version_art.id,
                    "anchor": f"shot_{i}",
                    "target_anchor": paras[r - 1]["id"],
                }
            )
    content = {
        "shots": shots,
        "paragraphs": [[paras[r - 1]["id"] for r in refs] for refs in para_refs],
        "total_seconds": round(sum(float(s["seconds"]) for s in shots), 2),
        "target_seconds": target,
        "version": version,
        "summary": summary,
    }
    return [ArtifactOut("storyboard", f"分镜 · v{version} · {len(shots)} 镜", content, links)]


async def artist(ctx: RoleContext) -> list[ArtifactOut]:
    from app.services import generation_service, project_service as ps
    from app.services.production_service import resolve_style

    board = ctx.latest("storyboard")
    if board is None:
        raise RoleError("没有分镜")
    project, output, version, spec = await _frozen(ctx)
    shots = (board.get("content") or {}).get("shots") or []
    settings = output.settings or {}
    assigned: dict[int, dict[str, Any]] = {}
    for a in (await ps.list_assets(ctx.db, project.id, role="keyframe"))["items"]:
        t = a.get("target") or {}
        shot = t.get("shot") if isinstance(t, dict) else None
        if str(shot or "").isdigit() and (not t.get("output_id") or t.get("output_id") == output.id):
            assigned[int(shot)] = a
    style = await resolve_style(ctx.db, project, ps.copy_brief(spec.get("brief")), settings)
    style_text = ""
    if style:
        style_text = "；".join(
            f"{k}: {style[k] if isinstance(style[k], str) else json.dumps(style[k], ensure_ascii=False)}"
            for k in ("name", "palette", "typography", "composition", "motion", "prompt")
            if style.get(k)
        )[:1500]
    need = [i for i in range(1, len(shots) + 1) if i not in assigned]
    prompts: dict[int, str] = {}
    if need and all(str(shots[i - 1].get("prompt") or "").strip() for i in need) and not style_text:
        prompts = {i: str(shots[i - 1]["prompt"]) for i in need}
    elif need:
        system = (
            "你是美术指导。为每个镜头写一张关键帧的生图提示词：主体、构图、色彩、光线、质感，"
            "画面内文字用「」标出且不超过 8 个字。风格规则必须体现在每条提示词里。"
            '只输出 JSON：{"frames": [{"shot": 镜头序号, "prompt": "…"}]}' + ctx.system_extra()
        )
        user = {
            "风格": style_text or "不指定",
            "画幅": settings.get("aspect_ratio") or "16:9",
            "镜头": [
                {
                    "shot": i,
                    "beat": shots[i - 1].get("beat"),
                    "visual": shots[i - 1].get("visual"),
                    "prompt": shots[i - 1].get("prompt"),
                }
                for i in need
            ],
        }
        reply = await _llm(
            ctx,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"运行 #{ctx.run_id}\n" + json.dumps(user, ensure_ascii=False)},
            ],
            scene="flow_artist",
            max_tokens=4000,
        )
        for f in (reply or {}).get("frames") or [] if isinstance(reply, dict) else []:
            if isinstance(f, dict) and str(f.get("shot") or "").isdigit() and int(f["shot"]) in need:
                prompts[int(f["shot"])] = str(f.get("prompt") or "").strip()[:2000]
        for i in need:
            prompts.setdefault(i, str(shots[i - 1].get("prompt") or shots[i - 1].get("visual") or ""))
    frames = []
    links: list[dict[str, Any]] = [{"relation": "derived_from", "target_type": "artifact", "target_id": board["id"]}]
    generated = 0
    gen_ok = await generation_service.available(ctx.db)
    for i in range(1, len(shots) + 1):
        if i in assigned:
            a = assigned[i]
            frames.append({"shot": i, "prompt": None, "library_item_id": a["library_item_id"], "source": "assigned"})
            links.append(
                {"relation": "uses", "target_type": "library", "target_id": a["library_item_id"], "anchor": f"shot_{i}"}
            )
            continue
        frame: dict[str, Any] = {"shot": i, "prompt": prompts.get(i) or "", "library_item_id": None, "source": "prompt"}
        if gen_ok and ctx.node.params.get("generate", True):
            item_id = await generation_service.keyframe_for_flow(
                ctx.db,
                project_id=project.id,
                output_id=output.id,
                shot=i,
                prompt=frame["prompt"],
                aspect_ratio=settings.get("aspect_ratio") or "16:9",
                run_id=ctx.run_id,
                step_id=ctx.step_id,
            )
            if item_id:
                frame.update({"library_item_id": item_id, "source": "generated"})
                links.append(
                    {"relation": "generated", "target_type": "library", "target_id": item_id, "anchor": f"shot_{i}"}
                )
                generated += 1
        frames.append(frame)
        links.append(
            {
                "relation": "derived_from",
                "target_type": "artifact",
                "target_id": board["id"],
                "anchor": f"shot_{i}",
                "target_anchor": f"shot_{i}",
            }
        )
    summary = f"{len(frames)} 张关键帧" + (
        f"，生成 {generated} 张" if generated else "，只给提示词" if not assigned else ""
    )
    return [ArtifactOut("keyframes", f"关键帧 · {len(frames)} 张", {"frames": frames, "summary": summary}, links)]


async def producer(ctx: RoleContext) -> list[ArtifactOut]:
    from app.services import production_service

    _pid, oid = await _ids(ctx)
    board = ctx.latest("storyboard")
    if board is None:
        raise RoleError("没有分镜")
    frames = ctx.latest("keyframes")
    qa = ctx.latest("qa_report")
    feedback = ((qa or {}).get("content") or {}).get("issues") or [] if qa else []
    try:
        result = await production_service.produce(
            ctx.db,
            output_id=oid,
            shots=(board.get("content") or {}).get("shots") or [],
            keyframes=((frames or {}).get("content") or {}).get("frames") or [],
            feedback=feedback,
            executor=ctx.executor if ctx.executor != "internal" else "deepseek_harness",
            run_id=ctx.run_id,
            step_id=ctx.step_id,
            attempt=ctx.round,
        )
    except RoleError:
        raise
    except Exception as exc:
        raise RoleError(str(exc) or exc.__class__.__name__) from exc
    links: list[dict[str, Any]] = [{"relation": "derived_from", "target_type": "artifact", "target_id": board["id"]}]
    if frames:
        links.append({"relation": "uses", "target_type": "artifact", "target_id": frames["id"]})
    if qa:
        links.append({"relation": "fixes", "target_type": "artifact", "target_id": qa["id"]})
    result["summary"] = (
        f"第 {ctx.round} 次制作完成"
        + ("（复用设计源码）" if result.get("reused_design") else "")
        + (f"，处理 {len(feedback)} 个质检问题" if feedback else "")
    )
    return [ArtifactOut("video", f"成片 · 第 {ctx.round} 版", result, links)]


async def qa(ctx: RoleContext) -> list[ArtifactOut]:
    from app.services import production_service

    video = ctx.latest("video")
    board = ctx.latest("storyboard")
    if video is None or board is None:
        raise RoleError("没有成片可检查")
    shots = (board.get("content") or {}).get("shots") or []
    report = await production_service.inspect(ctx.db, video.get("content") or {}, shots)
    bad = [c["label"] for c in report["checks"] if c["ok"] is False]
    report["summary"] = (
        "质检通过" if report["passed"] else f"未通过：{'、'.join(bad)}（{len(report['issues'])} 个问题）"
    )
    report["round"] = ctx.round
    report["video_artifact_id"] = video["id"]
    links = [{"relation": "reviews", "target_type": "artifact", "target_id": video["id"]}]
    for it in report["issues"]:
        if it.get("shot"):
            links.append(
                {
                    "relation": "reviews",
                    "target_type": "artifact",
                    "target_id": board["id"],
                    "anchor": it["id"],
                    "target_anchor": f"shot_{it['shot']}",
                }
            )
    return [ArtifactOut("qa_report", f"质检 · {'通过' if report['passed'] else '未通过'}", report, links)]


ROLES = {"storyboarder": storyboarder, "artist": artist, "producer": producer, "qa": qa}
