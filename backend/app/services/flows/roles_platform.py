"""平台改写流程的角色（改造方案 2.2）：平台编辑（按平台并行）→ 规则校验（写入平台版本产出物）。"""

from __future__ import annotations

from typing import Any

from app.services.flows.roles import ArtifactOut, RoleContext, RoleError, _llm

PLATFORM_LABELS = {"xhs": "小红书", "zhihu": "知乎", "wechat": "公众号"}


async def _project_spec(ctx: RoleContext) -> tuple[Any, dict, int | None, list[dict]]:
    from app.services import output_service as outs, project_service as ps

    pid = ctx.inputs.get("project_id")
    if not pid:
        raise RoleError("平台改写需要项目")
    project = await ps.get_project(ctx.db, int(pid))
    spec, version = await outs.base_spec(ctx.db, project)
    sources = await ps.list_sources(ctx.db, project.id)
    return project, spec, version, sources


async def platform_editor(ctx: RoleContext) -> list[ArtifactOut]:
    """一个分支一个平台：改写 → 超限时带着问题重写一次。"""
    from app.services import output_service as outs

    kind = ctx.branch or ""
    if kind not in PLATFORM_LABELS:
        raise RoleError(f"不支持的平台：{kind or '（空）'}")
    project, spec, version, sources = await _project_spec(ctx)
    messages = outs.platform_messages(kind, spec, sources)
    if ctx.system_extra():
        messages[0] = {**messages[0], "content": messages[0]["content"] + ctx.system_extra()}
    reply = await _llm(ctx, messages, scene="studio_platform", max_tokens=6000)
    if not isinstance(reply, dict) or not reply.get("body"):
        raise RoleError("模型没有返回正文")
    rounds = 1
    issues = outs.platform_issues(kind, reply)
    if issues:
        retry = await _llm(ctx, outs.retry_messages(messages, reply, issues), scene="studio_platform", max_tokens=6000)
        rounds = 2
        if isinstance(retry, dict) and retry.get("body"):
            reply = retry
    content = {
        "kind": kind,
        "project_id": project.id,
        "based_on_version": version,
        "reply": reply,
        "rewrites": rounds,
        "summary": f"{PLATFORM_LABELS[kind]}稿" + ("（超限重写过一次）" if rounds > 1 else ""),
    }
    return [ArtifactOut("platform_draft", f"{PLATFORM_LABELS[kind]}稿 · {project.title}"[:300], content)]


async def platform_checker(ctx: RoleContext) -> list[ArtifactOut]:
    """逐个平台按规则校验：仍超限的截断并提示；结果写进项目的平台版本产出物（没有就新建）。"""
    from sqlalchemy import select

    from app.models.project import ProjectOutput
    from app.services import output_service as outs, project_service as ps

    drafts = [a for a in ctx.input_artifacts if a["kind"] == "platform_draft"]
    if not drafts:
        raise RoleError("没有平台稿可校验")
    project, _spec, _version, sources = await _project_spec(ctx)
    targets = {str(k): int(v) for k, v in (ctx.inputs.get("output_ids") or {}).items() if v}
    results: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for art in drafts:
        c = art.get("content") or {}
        kind = c.get("kind")
        if kind not in PLATFORM_LABELS:
            continue
        content = outs.finalize_platform(kind, c.get("reply") or {}, sources)
        content["run_id"] = ctx.run_id
        output = None
        if kind in targets:
            output = await ctx.db.get(ProjectOutput, targets[kind])
            if output is not None and (output.project_id != project.id or output.kind != kind):
                output = None
        if output is None:  # 沿用最新一个还没发布的同平台版本，没有就新建
            output = (
                await ctx.db.execute(
                    select(ProjectOutput)
                    .where(ProjectOutput.project_id == project.id, ProjectOutput.kind == kind)
                    .where(ProjectOutput.status != "published")
                    .order_by(ProjectOutput.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if output is None:
            output = ProjectOutput(
                project_id=project.id,
                kind=kind,
                title=ps.OUTPUT_TITLES[kind],
                status="draft",
                content={},
                settings={},
            )
            ctx.db.add(output)
            await ctx.db.flush()
        await outs.save_platform(ctx.db, output, content, c.get("based_on_version"))
        warnings = content.get("warnings") or []
        results.append(
            {
                "kind": kind,
                "label": PLATFORM_LABELS[kind],
                "output_id": output.id,
                "passed": not [w for w in warnings if not w.startswith("已截断")],
                "truncated": any(w.startswith("已截断") for w in warnings),
                "warnings": warnings,
                "chars": len(content.get("body") or ""),
            }
        )
        links.append({"relation": "reviews", "target_type": "artifact", "target_id": art["id"]})
    ok = sum(1 for r in results if r["passed"] and not r["truncated"])
    summary = f"{len(results)} 个平台，{ok} 个直接通过" + (
        f"，{len(results) - ok} 个截断或仍有提示" if ok < len(results) else ""
    )
    content = {"project_id": project.id, "results": results, "summary": summary}
    return [ArtifactOut("platform_check", f"规则校验 · {project.title}"[:300], content, links)]


ROLES = {"platform_editor": platform_editor, "platform_checker": platform_checker}
