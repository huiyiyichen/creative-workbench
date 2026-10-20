"""Obsidian 双向同步（改造方案 6.8）。

工作台写入 vault 下的 ``创意工作台/``：``收藏/ 素材/ 提示词/ 仓库/ 随笔/ 项目/ 主题/ 报告/``，
素材缩略图放 ``_附件/``。同步一轮 = 先读回、再写出：

* 读回（只读你改过的文件：内容哈希与上次写出的不同）：
  - 条目笔记：frontmatter ``tags``、``## 我的笔记`` 正文及其中的 ``[[双链]]``。
  - 随笔日文件：带 ``^cw-<id>`` 的小节更新对应随笔；没有锚点的新小节成为新随笔。
  - ``创意工作台/`` 下你新建的笔记（不在工作台管理的目录里）作为随笔进入灵感库。
* 写出：结构化字段归工作台（frontmatter、``## 摘要``、``## 关联``）；``## 我的笔记`` 原样保留。

字段归属保证两边各改各的部分，不会互相覆盖。状态（每个文件上次写出的哈希）存在
``创意工作台/.cw/state.json``，Obsidian 不显示点开头的目录。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.daily_report import DailyReport
from app.models.dossier import TopicDossier
from app.models.library import LibraryItem, LibraryLink, LinkRelation, Note
from app.services import library_files

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
VAULT_KEY = "obsidian_vault"
APP_URL_KEY = "obsidian_app_url"
LAST_SYNC_KEY = "obsidian_last_sync"
DEFAULT_APP_URL = "http://localhost:3000"
ROOT = "创意工作台"
ATTACH = "_附件"
NOTES_DIR = "随笔"
FILE_NOTE_SOURCE = "obsidian-file"  # 在 Obsidian 新建的整篇笔记，不写进日文件

KIND_DIR = {
    "article": "收藏",
    "video": "收藏",
    "post": "收藏",
    "link": "收藏",
    "image": "收藏",
    "asset": "素材",
    "generated": "素材",
    "prompt": "提示词",
    "repo": "仓库",
}
MANAGED_DIRS = {"收藏", "素材", "提示词", "仓库", NOTES_DIR, "项目", "主题", "报告", ATTACH, ".cw"}
KIND_LABEL = {
    "article": "文章",
    "video": "视频",
    "post": "图文",
    "link": "链接",
    "image": "图片",
    "asset": "素材",
    "generated": "生成图",
    "prompt": "提示词",
    "repo": "仓库",
}
LICENSE_LABEL = {"own": "自有", "commercial": "可商用", "reference": "仅参考", "unknown": "未知", "ai": "AI 生成"}

SECTION_RE = re.compile(r"^## (.+?)\s*$", re.M)
NOTE_HEAD_RE = re.compile(r"^## (\d{1,2}):(\d{2})(?:\s+\^cw-(\d+))?\s*$", re.M)
WIKI_RE = re.compile(r"\[\[([^\[\]|]{1,160})(?:\|[^\]]*)?\]\]")
BAD_CHARS = re.compile(r'[\\/:*?"<>|#^\[\]\n\r\t]+')


class ObsidianError(Exception):
    pass


# ── 设置 ──


async def _setting(db: AsyncSession, key: str) -> str | None:
    row = await db.get(AppSetting, key)
    return (row.value or "").strip() or None if row else None


async def _set(db: AsyncSession, key: str, value: str | None) -> None:
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


async def get_settings(db: AsyncSession) -> dict[str, Any]:
    vault = await _setting(db, VAULT_KEY)
    return {
        "vault": vault,
        "vault_name": Path(vault).name if vault else None,
        "app_url": await _setting(db, APP_URL_KEY) or DEFAULT_APP_URL,
        "last_sync": await _setting(db, LAST_SYNC_KEY),
        "root": ROOT,
    }


async def set_settings(db: AsyncSession, vault: str | None, app_url: str | None = None) -> dict[str, Any]:
    vault = (vault or "").strip() or None
    if vault:
        p = Path(vault).expanduser()
        if not p.is_dir():
            raise ObsidianError(f"找不到这个文件夹：{vault}")
        (p / ROOT).mkdir(exist_ok=True)
    await _set(db, VAULT_KEY, vault)
    if app_url is not None:
        await _set(db, APP_URL_KEY, app_url.strip().rstrip("/") or None)
    await db.commit()
    return await get_settings(db)


def open_url(vault_name: str, rel_path: str) -> str:
    """``obsidian://open``：rel_path 相对 ``创意工作台/``。"""
    return f"obsidian://open?vault={quote(vault_name)}&file={quote(f'{ROOT}/{rel_path}')}"


# ── Markdown 工具 ──


def safe_name(title: str | None, fallback: str = "未命名") -> str:
    name = BAD_CHARS.sub(" ", title or "").strip(" .")
    name = re.sub(r"\s+", " ", name)[:80].strip(" .")
    return name or fallback


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            try:
                data = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                data = {}
            rest = text[end + 4 :]
            return (data if isinstance(data, dict) else {}), rest.lstrip("\n")
    return {}, text


def dump_frontmatter(data: dict[str, Any]) -> str:
    clean = {k: v for k, v in data.items() if v not in (None, "", [])}
    return "---\n" + yaml.safe_dump(clean, allow_unicode=True, sort_keys=False, width=1000).strip() + "\n---\n"


def sections(body: str) -> dict[str, str]:
    """``## 标题`` → 正文（去掉首尾空行）。"""
    out: dict[str, str] = {}
    marks = list(SECTION_RE.finditer(body))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out[m.group(1).strip()] = body[m.end() : end].strip("\n").rstrip()
    return out


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tags(value: Any) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,，\s]+", value)
    if not isinstance(value, list):
        return []
    out = []
    for t in value:
        s = str(t).strip().lstrip("#")
        if s and s not in out:
            out.append(s)
    return out


def _local(ts: datetime | None) -> datetime:
    ts = ts or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(LOCAL_TZ)


# ── 同步状态 ──


class _Vault:
    def __init__(self, vault: Path):
        self.root = vault / ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / ".cw" / "state.json"
        try:
            self.state: dict[str, Any] = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            self.state = {}
        self.hashes: dict[str, str] = self.state.setdefault("hashes", {})
        self.file_notes: dict[str, int] = self.state.setdefault("file_notes", {})
        self.written = 0

    def read(self, rel: str) -> str | None:
        p = self.root / rel
        try:
            return p.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def user_changed(self, rel: str) -> str | None:
        """上次写出后被你改过的文件内容；没改或不存在返回 None。"""
        text = self.read(rel)
        if text is None or self.hashes.get(rel) == _hash(text):
            return None
        return text

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        if self.read(rel) != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, "utf-8")
            self.written += 1
        self.hashes[rel] = _hash(text)

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), "utf-8")


# ── 读回 ──


def _day_rel(d: str) -> str:
    return f"{NOTES_DIR}/{d}.md"


def note_link(n: Note) -> str:
    return f"[[{_local(n.created_at).date().isoformat()}#^cw-{n.id}]]"


def parse_day_file(text: str) -> list[dict[str, Any]]:
    """随笔日文件 → 小节列表：{hh, mm, id|None, body}。"""
    _, body = split_frontmatter(text)
    marks = list(NOTE_HEAD_RE.finditer(body))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out.append(
            {
                "hh": int(m.group(1)),
                "mm": int(m.group(2)),
                "id": int(m.group(3)) if m.group(3) else None,
                "body": body[m.end() : end].strip(),
            }
        )
    return out


async def _resolve(db: AsyncSession, target: str, stems: dict[str, int]) -> tuple[str, int] | None:
    from app.services.notes import resolve_wikilink

    t = target.strip()
    stem = t.split("#", 1)[0].strip().rsplit("/", 1)[-1]
    if "#^cw-" not in t and stem in stems:
        return ("item", stems[stem])
    return await resolve_wikilink(db, t)


async def _read_items(db: AsyncSession, v: _Vault, stems: dict[str, int]) -> int:
    from app.services.library import ensure_link

    changed = 0
    items = (await db.execute(select(LibraryItem).where(LibraryItem.obsidian_path.is_not(None)))).scalars().all()
    for item in items:
        text = v.user_changed(item.obsidian_path or "")
        if text is None:
            continue
        fm, body = split_frontmatter(text)
        if "tags" in fm:
            item.tags = _tags(fm.get("tags")) or None
        mine = sections(body).get("我的笔记", "").strip()
        item.my_notes = mine or None
        old = (
            (
                await db.execute(
                    select(LibraryLink).where(
                        LibraryLink.from_type == "item",
                        LibraryLink.from_id == item.id,
                        LibraryLink.relation == LinkRelation.WIKILINK.value,
                    )
                )
            )
            .scalars()
            .all()
        )
        for link in old:
            await db.delete(link)
        await db.flush()
        for target in WIKI_RE.findall(mine):
            ref = await _resolve(db, target, stems)
            if ref and ref != ("item", item.id):
                await ensure_link(db, ("item", item.id), ref, LinkRelation.WIKILINK.value)
        # 读回的内容视为已同步，写出时以库里为准
        v.hashes[item.obsidian_path or ""] = _hash(text)
        changed += 1
    return changed


async def _read_days(db: AsyncSession, v: _Vault) -> dict[str, int]:
    from app.services.notes import create_note, update_note

    stats = {"notes_updated": 0, "notes_created": 0}
    day_dir = v.root / NOTES_DIR
    if not day_dir.is_dir():
        return stats
    for p in sorted(day_dir.glob("*.md")):
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", p.stem)
        if not m:
            continue
        rel = _day_rel(p.stem)
        text = v.user_changed(rel)
        if text is None:
            continue
        y, mo, d = (int(x) for x in m.groups())
        for sec in parse_day_file(text):
            if sec["id"]:
                note = await db.get(Note, sec["id"])
                if note is None or note.deleted_at is not None:
                    continue
                if sec["body"] and sec["body"] != (note.body or "").strip():
                    await update_note(db, note.id, sec["body"], from_obsidian=True)
                    stats["notes_updated"] += 1
            elif sec["body"]:
                try:
                    created = datetime(y, mo, d, min(sec["hh"], 23), min(sec["mm"], 59), tzinfo=LOCAL_TZ).astimezone(
                        UTC
                    )
                except ValueError:
                    created = None
                note = await create_note(db, sec["body"], source="obsidian", created_at=created)
                note.obsidian_synced_at = datetime.now(UTC)
                stats["notes_created"] += 1
        await db.commit()
    return stats


async def _read_new_files(db: AsyncSession, v: _Vault) -> int:
    """``创意工作台/`` 下你新建的笔记 → 随笔（整篇）；之后的修改也同步到这条随笔。"""
    from app.services.notes import create_note, update_note

    count = 0
    for p in v.root.rglob("*.md"):
        rel = p.relative_to(v.root).as_posix()
        if rel.split("/", 1)[0] in MANAGED_DIRS:
            continue
        text = v.user_changed(rel)
        if text is None:
            continue
        fm, body = split_frontmatter(text)
        content = f"{p.stem}\n\n{body.strip()}".strip()
        note_id = v.file_notes.get(rel)
        if note_id and await db.get(Note, note_id) is not None:
            await update_note(db, note_id, content, from_obsidian=True)
        elif body.strip() or fm:
            note = await create_note(db, content, source=FILE_NOTE_SOURCE)
            v.file_notes[rel] = note.id
        v.hashes[rel] = _hash(text)
        count += 1
    return count


# ── 写出 ──


def _assign_path(item: LibraryItem, taken: set[str]) -> str:
    folder = KIND_DIR.get(item.kind, "收藏")
    base = safe_name(item.title)
    rel = f"{folder}/{base}.md"
    n = 2
    while rel in taken:
        rel = f"{folder}/{base} {n}.md"
        n += 1
    return rel


def _stem(rel: str) -> str:
    return rel.rsplit("/", 1)[-1][:-3]


def _copy_thumb(v: _Vault, item: LibraryItem) -> str | None:
    rel_src = item.thumb_small or item.thumb_large
    if not rel_src:
        return None
    try:
        src = library_files.abs_path(rel_src)
    except Exception:  # noqa: BLE001
        logger.debug("忽略的异常（obsidian_sync.py）", exc_info=True)
        return None
    if not src.is_file():
        return None
    dest = v.root / ATTACH / src.name
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    return f"{ATTACH}/{src.name}"


def render_item(
    item: LibraryItem,
    *,
    app_url: str,
    links: list[str],
    my_notes: str | None,
    thumb: str | None,
) -> str:
    meta = item.meta or {}
    fm = {
        "cw_id": f"item-{item.id}",
        "类型": KIND_LABEL.get(item.kind, item.kind),
        "平台": item.platform,
        "链接": item.url or item.source_url,
        "作者": item.author,
        "发布时间": meta.get("published_at"),
        "收藏时间": _local(item.created_at).strftime("%Y-%m-%d %H:%M"),
        "tags": list(item.tags or []),
        "ai_tags": list(item.ai_tags or []),
        "授权": LICENSE_LABEL.get(item.license, item.license),
        "指标": meta.get("metrics"),
        "工作台": f"{app_url}/library?open={item.id}",
    }
    summary = item.ai_description or ""
    if not summary and item.body:
        summary = item.body if item.kind == "prompt" else item.body[:600]
    parts = [dump_frontmatter(fm), f"# {item.title}\n"]
    if thumb:
        parts.append(f"![[{thumb}]]\n")
    parts.append("## 摘要\n\n" + (summary.strip() or "（暂无）") + "\n")
    parts.append("## 我的笔记\n\n" + ((my_notes or "").strip() + "\n" if (my_notes or "").strip() else ""))
    parts.append("## 关联\n\n" + ("\n".join(f"- {line}" for line in links) + "\n" if links else "（暂无）\n"))
    return "\n".join(parts)


async def _link_rows(db: AsyncSession, kind: str, ids: list[int]) -> list[LibraryLink]:
    if not ids:
        return []
    return list(
        (
            await db.execute(
                select(LibraryLink).where(
                    or_(
                        (LibraryLink.from_type == kind) & LibraryLink.from_id.in_(ids),
                        (LibraryLink.to_type == kind) & LibraryLink.to_id.in_(ids),
                    )
                )
            )
        ).scalars()
    )


async def _write_items(db: AsyncSession, v: _Vault, app_url: str, items: list[LibraryItem]) -> None:
    by_id = {i.id: i for i in items}
    links = await _link_rows(db, "item", list(by_id))
    note_ids = {link.from_id for link in links if link.from_type == "note"} | {
        link.to_id for link in links if link.to_type == "note"
    }
    dossier_ids = {link.to_id for link in links if link.to_type == "dossier"} | {
        link.from_id for link in links if link.from_type == "dossier"
    }
    notes = (
        {n.id: n for n in (await db.execute(select(Note).where(Note.id.in_(note_ids)))).scalars()} if note_ids else {}
    )
    dossiers = (
        {d.id: d for d in (await db.execute(select(TopicDossier).where(TopicDossier.id.in_(dossier_ids)))).scalars()}
        if dossier_ids
        else {}
    )
    rel_label = {
        "extracted": "提取",
        "distilled": "提炼",
        "generated": "生成",
        "wikilink": "双链",
        "manual": "关联",
        "same_event": "同一事件",
        "same_tag": "同标签",
        "same_author": "同作者",
        "similar": "相似",
        "used_in_project": "用于项目",
    }

    def ref_md(kind: str, rid: int) -> str | None:
        if kind == "item" and rid in by_id and by_id[rid].obsidian_path:
            return f"[[{_stem(by_id[rid].obsidian_path or '')}]]"
        if kind == "note" and rid in notes and notes[rid].deleted_at is None:
            return note_link(notes[rid])
        if kind == "dossier" and rid in dossiers:
            return f"[[{safe_name(dossiers[rid].title)}]]"
        return None

    per_item: dict[int, list[str]] = defaultdict(list)
    for link in links:
        if link.relation == LinkRelation.WIKILINK.value and link.from_type == "item":
            continue  # 你在「我的笔记」里写的双链已在正文里
        for me_kind, me_id, other_kind, other_id in (
            (link.from_type, link.from_id, link.to_type, link.to_id),
            (link.to_type, link.to_id, link.from_type, link.from_id),
        ):
            if me_kind == "item" and me_id in by_id:
                md = ref_md(other_kind, other_id)
                if md:
                    line = f"{rel_label.get(link.relation, link.relation)}：{md}"
                    if line not in per_item[me_id]:
                        per_item[me_id].append(line)

    for item in items:
        rel = item.obsidian_path or ""
        existing = v.read(rel)
        mine = item.my_notes
        if existing is not None:
            mine = sections(split_frontmatter(existing)[1]).get("我的笔记", mine or "")
        text = render_item(item, app_url=app_url, links=per_item[item.id], my_notes=mine, thumb=_copy_thumb(v, item))
        v.write(rel, text)


def render_day(d: str, notes: list[Note]) -> str:
    parts = [f"# 随笔 {d}\n"]
    for n in sorted(notes, key=lambda x: (x.created_at, x.id)):
        t = _local(n.created_at).strftime("%H:%M")
        body = (n.body or "").strip()
        imgs = n.image_item_ids or []
        if imgs:
            body += "\n\n" + " ".join(f"![[{ATTACH}/img-{i}]]" for i in imgs)
        parts.append(f"## {t} ^cw-{n.id}\n\n{body}\n")
    return "\n".join(parts)


async def _write_days(db: AsyncSession, v: _Vault, items_by_id: dict[int, LibraryItem]) -> int:
    notes = (
        (
            await db.execute(
                select(Note).where(Note.deleted_at.is_(None), Note.source != FILE_NOTE_SOURCE).order_by(Note.created_at)
            )
        )
        .scalars()
        .all()
    )
    days: dict[str, list[Note]] = defaultdict(list)
    for n in notes:
        days[_local(n.created_at).date().isoformat()].append(n)
    for d, ns in days.items():
        text = render_day(d, ns)
        # 随笔里的图片：嵌入对应素材的缩略图
        for n in ns:
            for iid in n.image_item_ids or []:
                item = items_by_id.get(iid)
                thumb = _copy_thumb(v, item) if item else None
                text = text.replace(f"![[{ATTACH}/img-{iid}]]", f"![[{thumb}]]" if thumb else "")
        v.write(_day_rel(d), text)
    return len(days)


async def _write_dossiers(db: AsyncSession, v: _Vault, app_url: str, items: list[LibraryItem]) -> int:
    from app.services.dossiers import _dossier_content_ids, _mentioning_reports

    linked = await db.execute(
        select(LibraryLink.to_id)
        .where(LibraryLink.to_type == "dossier")
        .union(select(LibraryLink.from_id).where(LibraryLink.from_type == "dossier"))
    )
    linked_ids = set(linked.scalars())
    dossiers = (
        (
            await db.execute(
                select(TopicDossier).where(
                    TopicDossier.archived_at.is_(None),
                    or_(TopicDossier.followed.is_(True), TopicDossier.id.in_(linked_ids or {-1})),
                )
            )
        )
        .scalars()
        .all()
    )
    by_content = defaultdict(list)
    for it in items:
        if it.content_id and it.obsidian_path:
            by_content[it.content_id].append(it)
    by_id = {i.id: i for i in items}
    for d in dossiers:
        content_ids = set(await _dossier_content_ids(db, d))
        entry_lines = [f"[[{_stem(it.obsidian_path or '')}]]" for cid in content_ids for it in by_content.get(cid, [])]
        links = await _link_rows(db, "dossier", [d.id])
        note_lines: list[str] = []
        for link in links:
            other = (link.from_type, link.from_id) if link.to_type == "dossier" else (link.to_type, link.to_id)
            if other[0] == "item" and other[1] in by_id and by_id[other[1]].obsidian_path:
                md = f"[[{_stem(by_id[other[1]].obsidian_path or '')}]]"
                if md not in entry_lines:
                    entry_lines.append(md)
            elif other[0] == "note":
                n = await db.get(Note, other[1])
                if n is not None and n.deleted_at is None:
                    note_lines.append(note_link(n))
        reports = await _mentioning_reports(db, d.title)
        report_lines = [f"[[日报 {r['date']}]]" if r["kind"] == "daily" else r["label"] for r in reports]
        fm = {
            "cw_id": f"dossier-{d.id}",
            "类型": "专题",
            "状态": d.status,
            "关注": bool(d.followed),
            "首次出现": _local(d.first_seen_at).strftime("%Y-%m-%d") if d.first_seen_at else None,
            "工作台": f"{app_url}/dossiers/{d.id}",
        }

        def block(title: str, lines: list[str]) -> str:
            return f"## {title}\n\n" + ("\n".join(f"- {x}" for x in lines) if lines else "（暂无）") + "\n"

        text = "\n".join(
            [
                dump_frontmatter(fm),
                f"# {d.title}\n",
                block("条目", entry_lines),
                block("随笔", note_lines),
                block("报告", report_lines),
            ]
        )
        v.write(f"主题/{safe_name(d.title)}.md", text)
    return len(dossiers)


async def _write_reports(db: AsyncSession, v: _Vault, app_url: str, limit: int = 30) -> int:
    rows = (
        (
            await db.execute(
                select(DailyReport).order_by(DailyReport.report_date.desc(), DailyReport.generated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    for r in rows:
        if r.report_date in seen:
            continue
        seen.add(r.report_date)
        fm = {
            "cw_id": f"daily-{r.id}",
            "类型": "日报",
            "日期": r.report_date,
            "工作台": f"{app_url}/daily?date={r.report_date}",
        }
        text = (
            dump_frontmatter(fm)
            + f"\n# 日报 {r.report_date}\n\n"
            + ((r.overview or "").strip() or "（暂无概览）")
            + "\n"
        )
        v.write(f"报告/日报 {r.report_date}.md", text)
        if len(seen) >= limit:
            break
    return len(seen)


# ── 一轮同步 ──


async def sync_once(db: AsyncSession) -> dict[str, Any]:
    vault = await _setting(db, VAULT_KEY)
    if not vault:
        return {"enabled": False}
    vpath = Path(vault).expanduser()
    if not vpath.is_dir():
        raise ObsidianError(f"vault 不存在：{vault}")
    v = _Vault(vpath)
    app_url = await _setting(db, APP_URL_KEY) or DEFAULT_APP_URL

    items = (
        (await db.execute(select(LibraryItem).where(LibraryItem.archived_at.is_(None)).order_by(LibraryItem.id)))
        .scalars()
        .all()
    )
    stems = {_stem(i.obsidian_path): i.id for i in items if i.obsidian_path}

    # 1) 读回
    stats: dict[str, Any] = {"enabled": True, "items_read": await _read_items(db, v, stems)}
    await db.commit()
    stats.update(await _read_days(db, v))
    stats["files_read"] = await _read_new_files(db, v)
    await db.commit()

    # 2) 分配路径并写出
    taken = {i.obsidian_path for i in items if i.obsidian_path}
    for item in items:
        if not item.obsidian_path:
            item.obsidian_path = _assign_path(item, taken)
            taken.add(item.obsidian_path)
    await db.commit()
    await _write_items(db, v, app_url, list(items))
    stats["items"] = len(items)
    stats["days"] = await _write_days(db, v, {i.id: i for i in items})
    stats["topics"] = await _write_dossiers(db, v, app_url, list(items))
    stats["reports"] = await _write_reports(db, v, app_url)
    (v.root / "项目").mkdir(exist_ok=True)  # 项目笔记在阶段 4 写入
    stats["written"] = v.written
    v.save()
    await _set(db, LAST_SYNC_KEY, datetime.now(UTC).isoformat())
    await db.commit()
    return stats
