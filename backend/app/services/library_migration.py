"""旧收藏夹迁移（改造方案 6.9）与素材收件箱（6.2）。

迁移幂等：灵感库条目、风格与模板都记 ``legacy_favorite_id``，已迁移的跳过。

| 类型 | 去向 |
|---|---|
| content、video、audio、image | 灵感库；已上传的文件迁入 ``data/library/`` |
| trend、topic_group | 专题（关注） |
| book | 灵感库（链接） |
| template、style | 风格与模板（v1），key 保持 ``favorite:template:{id}`` / ``favorite:style:{id}``，旧工程引用不变 |
| author、creator、source、feed | 信源（订阅），有链接的才建 |
| project、work | 留在原表，阶段 4 / 5 的项目与作品「星标」接管 |
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.dossier import TopicDossier
from app.models.favorite import FavoriteItem
from app.models.library import ImportMethod, LibraryItem, LibraryKind
from app.models.source import Source
from app.models.styles import ContentTemplate, VisualStyle
from app.services import library_files

logger = logging.getLogger(__name__)

INBOX_KEY = "library_inbox_dir"
IMPORTED_DIR = "已导入"
MIGRATED_KEY = "favorites_migrated_at"


def _snapshot(f: FavoriteItem) -> dict[str, Any]:
    return f.snapshot if isinstance(f.snapshot, dict) else {}


def _legacy_file(f: FavoriteItem) -> Path | None:
    snap = _snapshot(f)
    rel = snap.get("local_path") or snap.get("relative_path")
    if not rel:
        return None
    from app.services.favorite_media import MEDIA_ROOT

    p = (MEDIA_ROOT / rel).resolve()
    return p if p.is_file() and p.is_relative_to(MEDIA_ROOT) else None


async def migrate_favorites(db: AsyncSession) -> dict[str, int]:
    from app.services.library import add_file
    from app.services.styles import create_style, create_template

    stats = {"library": 0, "dossiers": 0, "templates": 0, "styles": 0, "sources": 0, "skipped": 0}
    done_items = set(
        (
            await db.execute(select(LibraryItem.legacy_favorite_id).where(LibraryItem.legacy_favorite_id.is_not(None)))
        ).scalars()
    )
    done_tpl = set(
        (
            await db.execute(
                select(ContentTemplate.legacy_favorite_id).where(ContentTemplate.legacy_favorite_id.is_not(None))
            )
        ).scalars()
    )
    done_style = set(
        (
            await db.execute(select(VisualStyle.legacy_favorite_id).where(VisualStyle.legacy_favorite_id.is_not(None)))
        ).scalars()
    )
    favorites = (await db.execute(select(FavoriteItem).order_by(FavoriteItem.id))).scalars().all()
    for f in favorites:
        t = str(f.target_type)
        snap = _snapshot(f)
        try:
            if t in ("content", "video", "audio", "image", "book"):
                if f.id in done_items:
                    continue
                item: LibraryItem | None = None
                path = _legacy_file(f)
                if path is not None:
                    item = await add_file(
                        db,
                        path.read_bytes(),
                        path.name,
                        method=ImportMethod.MIGRATED.value,
                        title=f.title,
                        source_url=f.url,
                    )
                elif t == "content" and f.target_id:
                    from app.services.library import add_from_content

                    try:
                        item = await add_from_content(db, int(f.target_id), method=ImportMethod.MIGRATED.value)
                    except LookupError:
                        item = None
                if item is None:
                    kind = {"video": LibraryKind.VIDEO, "audio": LibraryKind.ASSET, "image": LibraryKind.ASSET}.get(
                        t, LibraryKind.LINK
                    )
                    item = LibraryItem(
                        kind=kind.value,
                        asset_kind={"audio": "audio", "image": "image"}.get(t),
                        title=f.title,
                        url=f.url,
                        cover_url=f.cover_url,
                        author=f.source_name,
                        import_method=ImportMethod.MIGRATED.value,
                    )
                    db.add(item)
                item.legacy_favorite_id = f.id
                item.my_notes = item.my_notes or f.note
                if isinstance(f.tags, list):
                    item.tags = list(dict.fromkeys([*(item.tags or []), *map(str, f.tags)]))
                item.created_at = f.created_at
                await db.flush()
                stats["library"] += 1
            elif t in ("trend", "topic_group"):
                exists = (
                    await db.execute(
                        select(TopicDossier.id).where(TopicDossier.kind == "manual", TopicDossier.title == f.title)
                    )
                ).first()
                if exists:
                    continue
                db.add(
                    TopicDossier(
                        kind="manual", title=f.title[:300], query=f.title[:255], followed=True, created_at=f.created_at
                    )
                )
                stats["dossiers"] += 1
            elif t == "template":
                if f.id in done_tpl:
                    continue
                entry = await create_template(
                    db,
                    f.title,
                    {
                        "purpose": f.note or snap.get("description"),
                        "structure": [{"title": b, "points": []} for b in snap.get("beats") or []],
                        "forms": snap.get("modes"),
                        "note": "从旧收藏夹迁移",
                    },
                    key=f"favorite:template:{f.id}",
                )
                row = (
                    await db.execute(select(ContentTemplate).where(ContentTemplate.key == entry["key"]))
                ).scalar_one()
                row.legacy_favorite_id = f.id
                stats["templates"] += 1
            elif t == "style":
                if f.id in done_style:
                    continue
                colors = [
                    c for c in snap.get("colors") or [] if isinstance(c, str) and len(c) == 7 and c.startswith("#")
                ]
                entry = await create_style(
                    db,
                    f.title,
                    {
                        "palette": [{"name": f"色 {i + 1}", "hex": c} for i, c in enumerate(colors)],
                        "layout_rules": "\n".join(snap.get("rules") or []),
                        "forms": ["music_video", "animation_video", "video_prompt"]
                        if snap.get("native_mv", True)
                        else ["video_prompt"],
                        "note": "从旧收藏夹迁移 · " + (f.note or snap.get("description") or ""),
                    },
                    key=f"favorite:style:{f.id}",
                )
                row = (await db.execute(select(VisualStyle).where(VisualStyle.key == entry["key"]))).scalar_one()
                row.legacy_favorite_id = f.id
                stats["styles"] += 1
            elif t in ("author", "creator", "source", "feed"):
                if not f.url:
                    stats["skipped"] += 1
                    continue
                if (await db.execute(select(Source.id).where(Source.url == f.url))).first():
                    continue
                from app.services.scrapers.recognizer import recognize_input

                rec = recognize_input(f.url)
                db.add(
                    Source(
                        name=f.title[:255],
                        url=rec.get("url") or f.url,
                        source_type=rec.get("source_type") or "RSS",
                        kind="subscription",
                        platform=rec.get("platform"),
                    )
                )
                stats["sources"] += 1
            else:
                stats["skipped"] += 1
        except Exception:  # noqa: BLE001 — 单条失败不影响其余
            logger.warning("favorite %s migration failed", f.id, exc_info=True)
            await db.rollback()
            stats["skipped"] += 1
    row = await db.get(AppSetting, MIGRATED_KEY)
    if row is None:
        db.add(AppSetting(key=MIGRATED_KEY, value=datetime.now(UTC).isoformat()))
    else:
        row.value = datetime.now(UTC).isoformat()
    await db.commit()
    return stats


# ── 素材收件箱 ───────────────────────────────────────────────────


async def inbox_dir(db: AsyncSession) -> Path | None:
    row = await db.get(AppSetting, INBOX_KEY)
    if row is None or not (row.value or "").strip():
        return None
    return Path(row.value.strip()).expanduser()


async def set_inbox_dir(db: AsyncSession, value: str | None) -> str | None:
    path = (value or "").strip() or None
    if path:
        p = Path(path).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        (p / IMPORTED_DIR).mkdir(exist_ok=True)
    row = await db.get(AppSetting, INBOX_KEY)
    if row is None:
        db.add(AppSetting(key=INBOX_KEY, value=path))
    else:
        row.value = path
    await db.commit()
    return path


async def scan_inbox(db: AsyncSession, *, limit: int = 50) -> dict[str, int]:
    """放进收件箱的文件自动导入，导入后移到其中的 ``已导入/``。失败的留在原地，下次再试。"""
    from app.services.library import LibraryError, add_file

    root = await inbox_dir(db)
    if root is None or not root.is_dir():
        return {"imported": 0, "failed": 0}
    done_dir = root / IMPORTED_DIR
    done_dir.mkdir(exist_ok=True)
    imported = failed = 0
    for p in sorted(root.iterdir()):
        if imported + failed >= limit:
            break
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() in (".tmp", ".part", ".crdownload"):
            continue
        if library_files.classify(p.name) == "file":
            continue
        try:
            await add_file(db, p.read_bytes(), p.name, method=ImportMethod.INBOX.value)
        except (LibraryError, OSError) as exc:
            logger.info("inbox import failed for %s: %s", p.name, exc)
            failed += 1
            continue
        target = done_dir / p.name
        if target.exists():
            target = done_dir / f"{p.stem}-{int(datetime.now(UTC).timestamp())}{p.suffix}"
        shutil.move(str(p), str(target))
        imported += 1
    return {"imported": imported, "failed": failed}
