"""产出物（设计文档 6.1、6.3、12 节）：平台改写、HTML 清洗、视频提示词包。

- 平台改写从定稿（未定稿时用工作副本）改写；模型返回结构化字段，超限时带着问题让模型重写一次，
  再超限就截断并把提示写进 ``content.warnings``。
- 公众号正文用 nh3 按白名单清洗后保存。
- 提示词包由 Jinja2 模板确定性生成，不调用模型；ZIP 含 README.md、script.md、storyboard.csv、style.json 和素材文件。
"""

from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from typing import Any

from jinja2 import ChainableUndefined, Environment
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ValidationError
from app.models.library import LibraryItem
from app.schemas.studio import StudioDraft
from app.services import output_rules as rules, project_service as ps

logger = logging.getLogger(__name__)


# ── HTML 清洗 ────────────────────────────────────────────────────────


def sanitize_wechat_html(html: str) -> str:
    import nh3

    return nh3.clean(
        html or "",
        tags=rules.WECHAT_TAGS,
        attributes=rules.WECHAT_ATTRS,
        url_schemes={"http", "https"},
        link_rel="noopener noreferrer",
    )


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def normalize_platform(kind: str, raw: dict) -> dict:
    """把模型结果规整成平台字段；超限截断并记提示。"""
    r = rules.PLATFORM_RULES[kind]
    tags = [str(t).strip().lstrip("#") for t in (raw.get("tags") or []) if str(t).strip()]
    content = {
        "title": str(raw.get("title") or "").strip(),
        "body": str(raw.get("body") or "").strip(),
        "tags": tags,
        "cover_text": str(raw.get("cover_text") or "").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "image_suggestions": [str(x).strip() for x in (raw.get("image_suggestions") or []) if str(x).strip()],
    }
    if kind in rules.SCRIPT_KINDS:
        content["hook"] = str(raw.get("hook") or "").strip()
    if kind == "wechat":
        content["body"] = sanitize_wechat_html(content["body"])
    warnings = [i["message"] for i in rules.check(kind, content)]
    if warnings:
        content["title"] = _truncate(content["title"], r["title_max"])
        if kind != "wechat":
            content["body"] = _truncate(content["body"], r["body_max"])
        if "cover_text_max" in r:
            content["cover_text"] = _truncate(content["cover_text"], r["cover_text_max"])
        if "summary_max" in r:
            content["summary"] = _truncate(content["summary"], r["summary_max"])
        if "hook_max" in r:
            content["hook"] = _truncate(content.get("hook", ""), r["hook_max"])
        if "tags_max" in r:
            content["tags"] = content["tags"][: r["tags_max"]]
        if "images_max" in r:
            content["image_suggestions"] = content["image_suggestions"][: r["images_max"]]
    content["warnings"] = [f"已截断：{w}" for w in warnings] + [i["message"] for i in rules.check(kind, content)]
    return content


def zhihu_with_sources(body: str, sources: list[dict]) -> str:
    if not sources or "## 来源" in body:
        return body
    lines = [
        f"{i + 1}. [{s['snapshot'].get('title') or '来源'}]({s['snapshot'].get('url') or ''})"
        for i, s in enumerate(sources)
    ]
    return body.rstrip() + "\n\n## 来源\n\n" + "\n".join(lines)


# ── 平台改写 ─────────────────────────────────────────────────────────


async def _call_model(messages: list[dict]) -> tuple[Any, dict]:
    from app.services.llm import provider

    return await provider.call_llm_json_with_metadata(
        messages, temperature=0.5, max_tokens=6000, scene="studio_platform", routing_group="default"
    )


async def base_spec(db: AsyncSession, project) -> tuple[dict, int | None]:
    if project.finalized_version:
        return await ps.finalized_spec(db, project), project.finalized_version
    return project.spec or {}, None


def platform_messages(kind: str, spec: dict, sources: list[dict]) -> list[dict]:
    """平台编辑的提示词（直接改写与平台改写流程共用）。"""
    draft = StudioDraft.model_validate(spec.get("draft") or {})
    if not draft.body.strip():
        raise ValidationError("文稿是空的，先写稿")
    r = rules.PLATFORM_RULES[kind]
    system = (
        f"你是{r['label']}编辑。把文稿改写成{r['label']}版本。规则：{r['guide']}" "事实只来自文稿和来源，不编造。"
    ) + (
        '只返回 JSON：{"title":"","hook":"","body":"","tags":[],"cover_text":"","summary":""}'
        if kind in rules.SCRIPT_KINDS
        else '只返回 JSON：{"title":"","body":"","tags":[],"cover_text":"","summary":"","image_suggestions":[]}'
    )
    user = json.dumps(
        {
            "brief": ps.copy_brief(spec.get("brief")),
            "title": draft.title,
            "logline": draft.logline,
            "body": draft.body,
            "sources": [{"title": s["snapshot"].get("title"), "url": s["snapshot"].get("url")} for s in sources],
        },
        ensure_ascii=False,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def platform_issues(kind: str, reply: dict) -> list[dict]:
    body = reply.get("body", "")
    return rules.check(kind, {**reply, "body": sanitize_wechat_html(body) if kind == "wechat" else body})


def retry_messages(messages: list[dict], reply: dict, issues: list[dict]) -> list[dict]:
    return messages + [
        {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)},
        {
            "role": "user",
            "content": "以下超出平台限制，请修改后重新返回完整 JSON：" + "；".join(i["message"] for i in issues),
        },
    ]


def finalize_platform(kind: str, reply: dict, sources: list[dict]) -> dict:
    content = normalize_platform(kind, reply)
    if kind == "zhihu":
        content["body"] = zhihu_with_sources(content["body"], sources)
    return content


async def save_platform(db: AsyncSession, output, content: dict, version: int | None) -> None:
    output.content = content
    output.based_on_version = version
    output.title = output.title or ps.OUTPUT_TITLES[output.kind]
    await db.commit()
    await _register_artifact(db, output, content, version)


async def generate_platform(db: AsyncSession, output_id: int) -> dict:
    output = await ps.get_output(db, output_id)
    if output.kind not in rules.PLATFORM_RULES:
        raise ValidationError("这个产出物不是平台版本")
    project = await ps.get_project(db, output.project_id)
    spec, version = await base_spec(db, project)
    sources = await ps.list_sources(db, project.id)
    messages = platform_messages(output.kind, spec, sources)
    meta: dict = {}
    try:
        reply, meta = await _call_model(messages)
        if not isinstance(reply, dict) or not reply.get("body"):
            raise ValueError("模型没有返回正文")
        issues = platform_issues(output.kind, reply)
        if issues:  # 带着问题重写一次
            retry, meta = await _call_model(retry_messages(messages, reply, issues))
            if isinstance(retry, dict) and retry.get("body"):
                reply = retry
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform rewrite failed: %s", str(exc)[:200])
        raise AppException("平台改写失败，请检查模型配置或稍后重试", 503, {"code": "model_unavailable"}) from exc
    content = finalize_platform(output.kind, reply, sources)
    content["model"] = (meta or {}).get("model")
    await save_platform(db, output, content, version)
    return await ps.output_view(db, output_id)


async def _register_artifact(db: AsyncSession, output, content: dict, version: int | None) -> None:
    """平台稿登记为产物（溯源：平台稿 ← 文稿版本 ← 来源）。失败不影响主流程。"""
    try:
        from app.services import project_lineage

        await project_lineage.register_platform(db, output, content, version)
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.debug("register platform artifact skipped", exc_info=True)


async def check_output(db: AsyncSession, output_id: int) -> dict:
    output = await ps.get_output(db, output_id)
    return {"issues": rules.check(output.kind, output.content or {})}


def platform_export(kind: str, content: dict, fmt: str) -> tuple[str, str]:
    title = content.get("title") or ""
    body = content.get("body") or ""
    if fmt == "html":
        html = body if kind == "wechat" else _md_to_html(body)
        return f"<h1>{_esc(title)}</h1>\n{html}", "text/html"
    tags = " ".join(f"#{t}" for t in content.get("tags") or [])
    head = f"# {title}\n\n"
    if kind in rules.SCRIPT_KINDS:
        for label, key in (("封面", "cover_text"), ("开头钩子", "hook"), ("简介", "summary")):
            if content.get(key):
                head += f"> {label}：{content[key]}\n\n"
    md = head + body + (f"\n\n{tags}" if tags else "")
    return md, "text/markdown"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_to_html(md: str) -> str:
    parts = []
    for para in ps.split_paragraphs(md):
        if para.startswith("### "):
            parts.append(f"<h3>{_esc(para[4:])}</h3>")
        elif para.startswith("## "):
            parts.append(f"<h2>{_esc(para[3:])}</h2>")
        elif para.startswith("> "):
            parts.append(f"<blockquote>{_esc(para[2:])}</blockquote>")
        else:
            parts.append(f"<p>{_esc(para)}</p>")
    return sanitize_wechat_html("\n".join(parts))


# ── 视频提示词包 ─────────────────────────────────────────────────────

BUNDLE_SECTIONS = ("script", "storyboard", "style", "assets", "delivery")
TARGET_NOTES = {
    "generic": "把以下内容交给任意视频生成工具或制作者。",
    "claude_code": "你是 Claude Code。请在当前目录用 Remotion 实现这支视频，完成后运行渲染并回传成片（工作台工具 upload_output 或在「回传成片」上传）。",
    "codex": "你是 Codex。请用 `codex exec` 在当前目录用 Remotion 实现这支视频，渲染 MP4 并回传。",
    "deepseek_harness": "DeepSeek Harness 读取 contract.json 与本说明，按分镜生成 Remotion 工程并渲染。",
}

_env = Environment(autoescape=False, undefined=ChainableUndefined, trim_blocks=True, lstrip_blocks=True)
_env.filters["cell"] = lambda v: str(v or "").replace("|", "／").replace("\n", " ")
BUNDLE_TEMPLATE = _env.from_string(
    """# {{ title }}

> {{ target_note }}

- 项目：#{{ project_id }}　定稿版本：v{{ version }}
- 内容形态：{{ brief.mode }}　目标时长：{{ brief.duration_seconds | int }} 秒
{% if brief.audience %}- 受众：{{ brief.audience }}
{% endif %}
{% if "script" in include %}
## 定稿脚本

{% if draft.logline %}**梗概**：{{ draft.logline }}

{% endif %}
{{ draft.body }}
{% endif %}
{% if "storyboard" in include and draft.shots %}

## 分镜表

| 镜 | 时长 | 画面 | 镜头与运动 | 旁白 / 声音 | 字幕 | 衔接 |
|---|---|---|---|---|---|---|
{% for s in draft.shots %}
| {{ loop.index }} | {{ "%.1f" | format(s.seconds) }}s | {{ s.visual | cell }} | {{ s.camera | cell }} | {{ s.audio | cell }} | {{ s.caption | cell }} | {{ s.transition | cell }} |
{% endfor %}

总时长 {{ "%.1f" | format(total_seconds) }} 秒
{% for s in draft.shots if s.prompt %}
{% if loop.first %}

### 逐镜生成提示词

{% endif %}
{{ loop.index }}. {{ s.prompt }}
{% endfor %}
{% endif %}
{% if "style" in include %}

## 风格规范

{% if style %}
- 风格：{{ style.get("name") or style.get("id") }}{% if style.get("version") %}（v{{ style.get("version") }}）{% endif %}

{% for k, v in style_rules %}
- {{ k }}：{{ v }}
{% endfor %}
{% else %}
- 未指定视觉风格，按内容自由设计。
{% endif %}
- 表现方案：{{ settings.presentation or "未指定" }}　画幅：{{ settings.aspect_ratio or "16:9" }}
{% endif %}
{% if "assets" in include %}

## 素材清单

{% for a in assets %}
- [{{ a.role }}] {{ a.title }}（授权：{{ a.license }}）{% if a.file %} → `assets/{{ a.file }}`{% endif %}

{% else %}
- （无）
{% endfor %}
{% endif %}
{% if "delivery" in include %}

## 交付要求

- 画幅 {{ settings.aspect_ratio or "16:9" }}，时长约 {{ brief.duration_seconds | int }} 秒
- 字幕：{{ "中英双语" if settings.bilingual else "中文" }}，同时输出 SRT
- 输出：MP4（H.264，30fps）+ 工程源码
{% endif %}
"""
)


async def _bundle_context(db: AsyncSession, output) -> dict:
    from app.services.studio_catalog import catalog_for_user, resolve

    project = await ps.get_project(db, output.project_id)
    spec = await ps.finalized_spec(db, project)
    brief = ps.copy_brief(spec.get("brief"))
    settings = output.settings or {}
    draft = StudioDraft.model_validate(spec.get("draft") or {})
    style = None
    if settings.get("style_id"):
        catalog = await catalog_for_user(db, project.owner_id)
        _t, style = resolve(ps.studio_brief(brief, settings), templates=catalog["templates"], styles=catalog["styles"])
    style_rules = []
    if style:
        for key in ("palette", "typography", "composition", "motion", "rules", "description", "prompt"):
            if style.get(key):
                value = style[key]
                style_rules.append((key, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)))
    assets = []
    for a in (await ps.list_assets(db, project.id))["items"]:
        item = a.get("item") or {}
        assets.append(
            {
                "role": a["role"],
                "title": item.get("title") or "",
                "license": item.get("license") or "unknown",
                "id": a["library_item_id"],
                "file": None,
            }
        )
    target = settings.get("target") or "generic"
    include = [s for s in (settings.get("include") or BUNDLE_SECTIONS) if s in BUNDLE_SECTIONS]
    return {
        "title": draft.title or project.title,
        "project_id": project.id,
        "version": project.finalized_version,
        "brief": brief,
        "draft": draft,
        "total_seconds": sum(s.seconds for s in draft.shots),
        "settings": settings,
        "style": style,
        "style_rules": style_rules,
        "assets": assets,
        "include": include,
        "target": target,
        "target_note": TARGET_NOTES.get(target, TARGET_NOTES["generic"]),
    }


def render_bundle_markdown(ctx: dict) -> str:
    import re

    md = BUNDLE_TEMPLATE.render(**ctx).strip()
    md = re.sub(r"\n(#{2,3} )", r"\n\n\1", md)  # 小节标题前留空行
    return re.sub(r"\n{3,}", "\n\n", md) + "\n"


async def bundle(db: AsyncSession, output_id: int, fmt: str = "md") -> tuple[bytes, str, str]:
    output = await ps.get_output(db, output_id)
    if output.kind not in {"prompt_bundle", "video", "mv"}:
        raise ValidationError("只有视频、MV 和提示词包能导出提示词包")
    ctx = await _bundle_context(db, output)
    name = f"project-{ctx['project_id']}-v{ctx['version']}"
    if fmt == "md":
        return render_bundle_markdown(ctx).encode("utf-8"), "text/markdown; charset=utf-8", f"{name}.md"
    from app.services.library_files import LibraryFileError, abs_path

    files: list[tuple[str, bytes]] = []
    for a in ctx["assets"]:
        item = await db.get(LibraryItem, a["id"])
        if item and item.file_path:
            try:
                path = abs_path(item.file_path)
            except LibraryFileError:
                continue
            if path.is_file():
                fname = f"{a['id']}-{(item.file_name or path.name)}"
                a["file"] = fname
                files.append((f"assets/{fname}", path.read_bytes()))
    md = render_bundle_markdown(ctx)
    draft: StudioDraft = ctx["draft"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["index", "seconds", "beat", "visual", "camera", "audio", "caption", "transition", "prompt"])
    for i, s in enumerate(draft.shots, 1):
        writer.writerow([i, s.seconds, s.beat, s.visual, s.camera, s.audio, s.caption, s.transition, s.prompt])
    style_json = {
        "style": ctx["style"],
        "presentation": ctx["settings"].get("presentation"),
        "aspect_ratio": ctx["settings"].get("aspect_ratio") or "16:9",
        "bilingual": bool(ctx["settings"].get("bilingual")),
    }
    script = f"# {ctx['title']}\n\n{draft.logline}\n\n{draft.body}\n".replace("\n\n\n", "\n\n")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", md)
        zf.writestr("script.md", script)
        zf.writestr("storyboard.csv", "\ufeff" + buf.getvalue())
        zf.writestr("style.json", json.dumps(style_json, ensure_ascii=False, indent=2))
        for path, data in files:
            zf.writestr(path, data)
    if output.kind == "prompt_bundle" and output.status == "draft":
        output.status = "exported"
        output.based_on_version = ctx["version"]
        await db.commit()
    return out.getvalue(), "application/zip", f"{name}.zip"
