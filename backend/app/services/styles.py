"""风格与模板（改造方案 6.6）：内置种子、新建、版本、复制、归档、从素材提炼、按名称 AI 生成；
以及给工作台 ``/studio/catalog`` 用的目录（返回形状不变）。
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import LibraryItem, LinkRelation
from app.models.styles import ContentTemplate, ContentTemplateVersion, VisualStyle, VisualStyleVersion

logger = logging.getLogger(__name__)

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class StyleError(ValueError):
    pass


class StyleNotFoundError(LookupError):
    pass


# ── 种子（内置，按 key 幂等） ──────────────────────────────────────


async def seed_builtins(db: AsyncSession) -> dict[str, int]:
    from app.services.studio_catalog import STYLES, TEMPLATES

    created = 0
    for t in TEMPLATES:
        if (await db.execute(select(ContentTemplate.id).where(ContentTemplate.key == t["id"]))).first():
            continue
        row = ContentTemplate(key=t["id"], name=t["name"], builtin=True, current_version=1)
        db.add(row)
        await db.flush()
        db.add(
            ContentTemplateVersion(
                template_id=row.id,
                version=1,
                purpose=t.get("description"),
                structure=[{"title": b, "points": []} for b in t.get("beats", [])],
                forms=t.get("modes"),
                note=f"内置 · {t.get('category') or ''}",
            )
        )
        created += 1
    for s in STYLES:
        if (await db.execute(select(VisualStyle.id).where(VisualStyle.key == s["id"]))).first():
            continue
        row = VisualStyle(key=s["id"], name=s["name"], builtin=True, current_version=1)
        db.add(row)
        await db.flush()
        roles = {"background": "背景", "foreground": "前景", "accent": "强调", "secondary": "辅助"}
        palette = [{"name": roles[k], "hex": s[k]} for k in roles if s.get(k)]
        db.add(
            VisualStyleVersion(
                style_id=row.id,
                version=1,
                palette=palette,
                layout_rules="\n".join(s.get("rules", [])),
                motion_rules=None,
                forms=["music_video", "animation_video", "video_prompt"] if s.get("native_mv") else ["video_prompt"],
                note=f"内置 · {s.get('category') or ''} · {s.get('description') or ''}",
            )
        )
        created += 1
    await db.commit()
    return {"created": created}


# ── 视图 ─────────────────────────────────────────────────────────


def _tpl_version_view(v: ContentTemplateVersion) -> dict[str, Any]:
    return {
        "version": v.version,
        "purpose": v.purpose,
        "audience": v.audience,
        "structure": v.structure or [],
        "tone": v.tone,
        "reference_snippets": v.reference_snippets or [],
        "forms": v.forms or [],
        "recommended_style_key": v.recommended_style_key,
        "cover_item_id": v.cover_item_id,
        "note": v.note,
        "created_at": v.created_at,
    }


def _style_version_view(v: VisualStyleVersion) -> dict[str, Any]:
    return {
        "version": v.version,
        "palette": v.palette or [],
        "fonts": v.fonts or [],
        "layout_rules": v.layout_rules,
        "motion_rules": v.motion_rules,
        "reference_item_ids": v.reference_item_ids or [],
        "forms": v.forms or [],
        "note": v.note,
        "created_at": v.created_at,
    }


async def _tpl_current(db: AsyncSession, t: ContentTemplate) -> ContentTemplateVersion | None:
    return (
        await db.execute(
            select(ContentTemplateVersion).where(
                ContentTemplateVersion.template_id == t.id, ContentTemplateVersion.version == t.current_version
            )
        )
    ).scalar_one_or_none()


async def _style_current(db: AsyncSession, s: VisualStyle) -> VisualStyleVersion | None:
    return (
        await db.execute(
            select(VisualStyleVersion).where(
                VisualStyleVersion.style_id == s.id, VisualStyleVersion.version == s.current_version
            )
        )
    ).scalar_one_or_none()


async def list_templates(db: AsyncSession, *, include_builtin: bool = True) -> list[dict[str, Any]]:
    stmt = select(ContentTemplate).where(ContentTemplate.archived_at.is_(None))
    if not include_builtin:
        stmt = stmt.where(ContentTemplate.builtin.is_(False))
    out = []
    for t in (await db.execute(stmt.order_by(ContentTemplate.builtin.desc(), ContentTemplate.id))).scalars():
        v = await _tpl_current(db, t)
        out.append(
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "builtin": t.builtin,
                "current_version": t.current_version,
                "current": _tpl_version_view(v) if v else None,
            }
        )
    return out


async def list_styles(db: AsyncSession, *, include_builtin: bool = True) -> list[dict[str, Any]]:
    stmt = select(VisualStyle).where(VisualStyle.archived_at.is_(None))
    if not include_builtin:
        stmt = stmt.where(VisualStyle.builtin.is_(False))
    out = []
    for s in (await db.execute(stmt.order_by(VisualStyle.builtin.desc(), VisualStyle.id))).scalars():
        v = await _style_current(db, s)
        out.append(
            {
                "id": s.id,
                "key": s.key,
                "name": s.name,
                "builtin": s.builtin,
                "current_version": s.current_version,
                "current": _style_version_view(v) if v else None,
            }
        )
    return out


async def get_template(db: AsyncSession, key: str) -> dict[str, Any]:
    t = (await db.execute(select(ContentTemplate).where(ContentTemplate.key == key))).scalar_one_or_none()
    if t is None:
        raise StyleNotFoundError(key)
    versions = (
        (
            await db.execute(
                select(ContentTemplateVersion)
                .where(ContentTemplateVersion.template_id == t.id)
                .order_by(ContentTemplateVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "builtin": t.builtin,
        "current_version": t.current_version,
        "archived_at": t.archived_at,
        "copied_from": t.copied_from,
        "versions": [_tpl_version_view(v) for v in versions],
    }


async def get_style(db: AsyncSession, key: str) -> dict[str, Any]:
    s = (await db.execute(select(VisualStyle).where(VisualStyle.key == key))).scalar_one_or_none()
    if s is None:
        raise StyleNotFoundError(key)
    versions = (
        (
            await db.execute(
                select(VisualStyleVersion)
                .where(VisualStyleVersion.style_id == s.id)
                .order_by(VisualStyleVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": s.id,
        "key": s.key,
        "name": s.name,
        "builtin": s.builtin,
        "current_version": s.current_version,
        "archived_at": s.archived_at,
        "copied_from": s.copied_from,
        "versions": [_style_version_view(v) for v in versions],
    }


# ── 新建 / 新版本 / 复制 / 归档 ────────────────────────────────────


def _slug(name: str, prefix: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", name).strip("-").lower()[:40] or prefix
    return f"{prefix}-{base}-{int(datetime.now(UTC).timestamp() * 1000) % 10_000_000}"


TEMPLATE_FIELDS = (
    "purpose",
    "audience",
    "structure",
    "tone",
    "reference_snippets",
    "forms",
    "recommended_style_key",
    "cover_item_id",
    "note",
)
STYLE_FIELDS = ("palette", "fonts", "layout_rules", "motion_rules", "reference_item_ids", "forms", "note")


def _check_palette(palette: Any) -> None:
    for c in palette or []:
        h = c.get("hex") if isinstance(c, dict) else c
        if not isinstance(h, str) or not HEX.match(h):
            raise StyleError(f"色值 {h!r} 应为 #rrggbb")


async def create_template(
    db: AsyncSession, name: str, fields: dict[str, Any], *, key: str | None = None, copied_from: str | None = None
) -> dict[str, Any]:
    if not name.strip():
        raise StyleError("名称不能为空")
    t = ContentTemplate(
        key=key or _slug(name, "tpl"), name=name.strip()[:200], current_version=1, copied_from=copied_from
    )
    db.add(t)
    await db.flush()
    db.add(ContentTemplateVersion(template_id=t.id, version=1, **{k: fields.get(k) for k in TEMPLATE_FIELDS}))
    await db.commit()
    return await get_template(db, t.key)


async def create_style(
    db: AsyncSession, name: str, fields: dict[str, Any], *, key: str | None = None, copied_from: str | None = None
) -> dict[str, Any]:
    if not name.strip():
        raise StyleError("名称不能为空")
    _check_palette(fields.get("palette"))
    s = VisualStyle(
        key=key or _slug(name, "style"), name=name.strip()[:200], current_version=1, copied_from=copied_from
    )
    db.add(s)
    await db.flush()
    db.add(VisualStyleVersion(style_id=s.id, version=1, **{k: fields.get(k) for k in STYLE_FIELDS}))
    await db.commit()
    for iid in fields.get("reference_item_ids") or []:
        await _link_reference(db, iid, ("style", s.id))
    return await get_style(db, s.key)


async def _link_reference(db: AsyncSession, item_id: int, target: tuple[str, int]) -> None:
    from app.services.library import ensure_link

    if await db.get(LibraryItem, item_id) is not None:
        await ensure_link(db, ("item", item_id), target, LinkRelation.DISTILLED.value)
        await db.commit()


async def add_template_version(db: AsyncSession, key: str, fields: dict[str, Any]) -> dict[str, Any]:
    """编辑即新版本；编辑内置模板时复制成自定义模板（6.6）。"""
    t = (await db.execute(select(ContentTemplate).where(ContentTemplate.key == key))).scalar_one_or_none()
    if t is None:
        raise StyleNotFoundError(key)
    current = await _tpl_current(db, t)
    base = _tpl_version_view(current) if current else {}
    merged = {k: fields.get(k, base.get(k)) for k in TEMPLATE_FIELDS}
    if t.builtin:
        return await create_template(db, f"{t.name}（我的）", merged, copied_from=t.key)
    t.current_version += 1
    db.add(ContentTemplateVersion(template_id=t.id, version=t.current_version, **merged))
    if fields.get("name"):
        t.name = str(fields["name"])[:200]
    await db.commit()
    return await get_template(db, key)


async def add_style_version(db: AsyncSession, key: str, fields: dict[str, Any]) -> dict[str, Any]:
    s = (await db.execute(select(VisualStyle).where(VisualStyle.key == key))).scalar_one_or_none()
    if s is None:
        raise StyleNotFoundError(key)
    current = await _style_current(db, s)
    base = _style_version_view(current) if current else {}
    merged = {k: fields.get(k, base.get(k)) for k in STYLE_FIELDS}
    _check_palette(merged.get("palette"))
    if s.builtin:
        return await create_style(db, f"{s.name}（我的）", merged, copied_from=s.key)
    s.current_version += 1
    db.add(VisualStyleVersion(style_id=s.id, version=s.current_version, **merged))
    if fields.get("name"):
        s.name = str(fields["name"])[:200]
    await db.commit()
    return await get_style(db, key)


async def copy_entry(db: AsyncSession, kind: str, key: str) -> dict[str, Any]:
    if kind == "template":
        src = await get_template(db, key)
        return await create_template(
            db, f"{src['name']} 副本", {k: src["versions"][0].get(k) for k in TEMPLATE_FIELDS}, copied_from=key
        )
    src = await get_style(db, key)
    return await create_style(
        db, f"{src['name']} 副本", {k: src["versions"][0].get(k) for k in STYLE_FIELDS}, copied_from=key
    )


async def archive_entry(db: AsyncSession, kind: str, key: str) -> None:
    model = ContentTemplate if kind == "template" else VisualStyle
    row = (await db.execute(select(model).where(model.key == key))).scalar_one_or_none()
    if row is None:
        raise StyleNotFoundError(key)
    if row.builtin:
        raise StyleError("内置的不能归档")
    row.archived_at = datetime.now(UTC)
    await db.commit()


# ── 提炼（AI） ──────────────────────────────────────────────────


def _distill_messages(kind: str, name: str, items: list[LibraryItem]) -> list[dict[str, str]]:
    lines = []
    for it in items[:12]:
        bits = [f"标题：{it.title}"]
        if it.palette:
            bits.append("配色：" + "、".join(it.palette))
        if it.ai_description:
            bits.append("描述：" + it.ai_description[:200])
        if it.body:
            bits.append("正文：" + it.body[:300])
        if it.tags:
            bits.append("标签：" + "、".join(map(str, it.tags[:6])))
        lines.append("；".join(bits))
    refs = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))
    if kind == "style":
        schema = '{"name": "风格名", "palette": [{"name": "用途", "hex": "#rrggbb"}], "fonts": [{"role": "标题/正文", "family": "字体名"}], "layout_rules": "版式与构图规则，分行", "motion_rules": "动效规则，分行"}'
        task = "把这些素材共同的视觉语言写成可执行的视觉风格规则（色板、字体、版式与构图、动效）"
    else:
        schema = '{"name": "模板名", "purpose": "用途", "audience": "受众", "structure": [{"title": "段落", "points": ["要点"]}], "tone": "语气"}'
        task = "把这些参考内容共同的结构和语气写成可复用的内容模板"
    return [
        {"role": "system", "content": "你是资深的视觉与内容设计师。只输出 JSON，不要解释。"},
        {"role": "user", "content": f"{task}。名称参考：「{name}」。\n参考：\n{refs}\n\n输出 JSON：{schema}"},
    ]


async def distill(db: AsyncSession, kind: str, name: str, item_ids: list[int] | None = None) -> dict[str, Any]:
    """从素材提炼为风格 / 模板；没给素材时读带同名标签的收藏作参考（6.6「AI 生成」）。素材作为参考保持关联。"""
    from app.services.library import json_has
    from app.services.llm import provider

    if item_ids:
        items = list((await db.execute(select(LibraryItem).where(LibraryItem.id.in_(item_ids)))).scalars())
    else:
        items = list(
            (
                await db.execute(
                    select(LibraryItem)
                    .where(LibraryItem.archived_at.is_(None), json_has(LibraryItem.tags, name))
                    .order_by(LibraryItem.created_at.desc())
                    .limit(12)
                )
            ).scalars()
        )
    result = await provider.call_llm_json(
        _distill_messages(kind, name, items), temperature=0.4, max_tokens=1500, scene="distill_style"
    )
    if not isinstance(result, dict):
        raise StyleError("模型没有返回可用的规则")
    ref_ids = [it.id for it in items]
    final_name = str(result.get("name") or name)
    if kind == "style":
        palette = [p for p in result.get("palette") or [] if isinstance(p, dict) and HEX.match(str(p.get("hex", "")))]
        entry = await create_style(
            db,
            final_name,
            {
                "palette": palette,
                "fonts": result.get("fonts") or [],
                "layout_rules": result.get("layout_rules"),
                "motion_rules": result.get("motion_rules"),
                "reference_item_ids": ref_ids,
                "note": f"从 {len(ref_ids)} 条素材提炼",
            },
        )
    else:
        entry = await create_template(
            db,
            final_name,
            {
                "purpose": result.get("purpose"),
                "audience": result.get("audience"),
                "structure": result.get("structure") or [],
                "tone": result.get("tone"),
                "note": f"从 {len(ref_ids)} 条素材提炼",
            },
        )
        t = (await db.execute(select(ContentTemplate).where(ContentTemplate.key == entry["key"]))).scalar_one()
        for iid in ref_ids:
            await _link_reference(db, iid, ("template", t.id))
    return {**entry, "reference_count": len(ref_ids)}


# ── 工作台目录（形状不变） ─────────────────────────────────────────


async def catalog_entries(db: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    """``/studio/catalog`` 用：模板 {id,name,category,description,image,modes,beats,custom}；风格 {id,…,colors,background,…}。"""
    templates = []
    for t in await list_templates(db):
        v = t["current"] or {}
        templates.append(
            {
                "id": t["key"],
                "name": t["name"],
                "category": "内置" if t["builtin"] else "我的模板",
                "description": v.get("purpose") or "",
                "image": None,
                "modes": v.get("forms") or ["animation_video", "video_prompt", "article", "music_video"],
                "beats": [s.get("title") for s in v.get("structure") or [] if isinstance(s, dict) and s.get("title")]
                or ["建立切口", "展开内容", "落到行动"],
                "custom": not t["builtin"],
                "version": t["current_version"],
            }
        )
    styles = []
    for s in await list_styles(db):
        v = s["current"] or {}
        colors = [p.get("hex") for p in v.get("palette") or [] if isinstance(p, dict) and p.get("hex")] or [
            "#F1F5F9",
            "#2563EB",
            "#0F172A",
        ]
        while len(colors) < 3:
            colors.append(colors[-1])
        styles.append(
            {
                "id": s["key"],
                "name": s["name"],
                "category": "内置" if s["builtin"] else "我的风格",
                "description": (v.get("note") or "").split("·")[-1].strip(),
                "image": None,
                "colors": colors,
                "background": colors[0],
                "foreground": colors[-1] if len(colors) < 4 else colors[1],
                "accent": colors[2] if len(colors) >= 4 else colors[1],
                "secondary": colors[3] if len(colors) >= 4 else colors[-1],
                "rules": [r for r in (v.get("layout_rules") or "").split("\n") if r.strip()] or ["信息层级清晰"],
                "native_mv": "music_video" in (v.get("forms") or []),
                "custom": not s["builtin"],
                "version": s["current_version"],
            }
        )
    return {"templates": templates, "styles": styles}
