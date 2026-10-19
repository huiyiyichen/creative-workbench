"""灵感库（6）、随笔（6.4）、风格与模板（6.6）接口。

浏览器扩展（Edge）只调用本机工作台的 ``/library/extension/*``；CORS 放行扩展来源。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services import library as lib, library_migration as migration, notes as notes_svc, styles as styles_svc
from app.services.library_files import LibraryFileError, abs_path

router = APIRouter(tags=["library"], dependencies=[Depends(get_current_user)])

MAX_UPLOAD = 500 * 1024 * 1024


def _bad(exc: Exception, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


# ── 条目 ──


class FromContentBody(BaseModel):
    content_id: int


class FromLinkBody(BaseModel):
    url: str = Field(..., max_length=2048)
    note: str | None = Field(None, max_length=2000)


class TextBody(BaseModel):
    text: str = Field(..., max_length=20000)
    kind: Literal["prompt", "link", "article"] = "prompt"
    title: str | None = Field(None, max_length=500)
    source_url: str | None = Field(None, max_length=2048)


class ItemPatch(BaseModel):
    title: str | None = Field(None, max_length=500)
    tags: list[str] | None = None
    license: Literal["own", "commercial", "reference", "unknown", "ai"] | None = None
    my_notes: str | None = None
    starred: bool | None = None
    body: str | None = None
    meta: dict[str, Any] | None = None


class BulkLicenseBody(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=1000)
    license: Literal["own", "commercial", "reference", "unknown", "ai"]


class LinkBody(BaseModel):
    to_type: Literal["item", "note", "content", "dossier", "project", "style", "template"]
    to_id: int


class FrameBody(BaseModel):
    content_id: int | None = None
    image_url: str | None = Field(None, max_length=2048)
    item_id: int | None = None
    at: float | None = Field(None, ge=0)


@router.get("/library/items")
async def list_library(
    kind: str | None = Query(None, max_length=16),
    asset_kind: str | None = Query(None, max_length=16),
    platform: str | None = Query(None, max_length=50),
    license: str | None = Query(None, max_length=16),
    tag: str | None = Query(None, max_length=60),
    q: str | None = Query(None, max_length=200),
    color: str | None = Query(None, max_length=7),
    board_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await lib.list_items(
            db,
            kind=kind,
            asset_kind=asset_kind,
            platform=platform,
            license=license,
            tag=tag,
            q=q,
            color=color,
            board_id=board_id,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )
    except lib.LibraryError as exc:
        raise _bad(exc) from exc


@router.get("/library/facets")
async def library_facets(db: AsyncSession = Depends(get_db)):
    return await lib.facets(db)


@router.post("/library/items/from-content")
async def library_from_content(body: FromContentBody, db: AsyncSession = Depends(get_db)):
    try:
        item = await lib.add_from_content(db, body.content_id)
    except lib.LibraryNotFoundError as exc:
        raise _bad(exc, 404) from exc
    return lib.item_view(item)


@router.post("/library/items/from-link")
async def library_from_link(body: FromLinkBody, db: AsyncSession = Depends(get_db)):
    try:
        item = await lib.add_from_link(db, body.url, note=body.note)
    except lib.LibraryError as exc:
        raise _bad(exc) from exc
    return lib.item_view(item)


@router.post("/library/items/text")
async def library_text(body: TextBody, db: AsyncSession = Depends(get_db)):
    try:
        item = await lib.add_text(
            db, body.text, kind=body.kind, title=body.title, source_url=body.source_url, method="clipboard"
        )
    except lib.LibraryError as exc:
        raise _bad(exc) from exc
    return lib.item_view(item)


@router.post("/library/items/upload")
async def library_upload(
    files: list[UploadFile] = File(...),
    method: Literal["file", "clipboard", "extension"] = Form("file"),
    license: Literal["own", "commercial", "reference", "unknown", "ai"] | None = Form(None),
    source_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """本地文件 / 剪贴板 / 拖入：可多个文件（拖入文件夹时前端逐个上传）。"""
    out, errors = [], []
    for f in files[:200]:
        data = await f.read(MAX_UPLOAD + 1)
        try:
            item = await lib.add_file(
                db,
                data,
                f.filename or "file",
                mime=f.content_type,
                method=method,
                license=license,
                source_url=source_url,
            )
            out.append(lib.item_view(item))
        except lib.LibraryError as exc:
            errors.append({"file": f.filename, "error": str(exc)})
    return {"items": out, "errors": errors}


@router.post("/library/items/frame")
async def library_frame(body: FrameBody, db: AsyncSession = Depends(get_db)):
    """从内容取图：文章配图 / 封面，或灵感库视频片段截帧。"""
    try:
        if body.item_id is not None and body.at is not None:
            item = await lib.add_video_frame(db, body.item_id, body.at)
        elif body.content_id is not None:
            item = await lib.add_frame_from_content(db, body.content_id, body.image_url)
        else:
            raise lib.LibraryError("需要 content_id，或 item_id + at")
    except lib.LibraryNotFoundError as exc:
        raise _bad(exc, 404) from exc
    except lib.LibraryError as exc:
        raise _bad(exc) from exc
    return lib.item_view(item)


@router.get("/library/items/{item_id}")
async def library_item(item_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await lib.get_item(db, item_id)
    except lib.LibraryNotFoundError as exc:
        raise _bad(exc, 404) from exc


@router.patch("/library/items/{item_id}")
async def library_patch(item_id: int, body: ItemPatch, db: AsyncSession = Depends(get_db)):
    try:
        item = await lib.update_item(db, item_id, body.model_dump(exclude_none=True))
    except lib.LibraryNotFoundError as exc:
        raise _bad(exc, 404) from exc
    except lib.LibraryError as exc:
        raise _bad(exc) from exc
    return lib.item_view(item)


@router.delete("/library/items/{item_id}")
async def library_delete(item_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await lib.archive_item(db, item_id)
    except lib.LibraryNotFoundError as exc:
        raise _bad(exc, 404) from exc
    return {"ok": True}


@router.post("/library/items/bulk-license")
async def library_bulk_license(body: BulkLicenseBody, db: AsyncSession = Depends(get_db)):
    return {"updated": await lib.bulk_license(db, body.ids, body.license)}


@router.post("/library/items/{item_id}/links")
async def library_link(item_id: int, body: LinkBody, db: AsyncSession = Depends(get_db)):
    await lib.link_items(db, ("item", item_id), (body.to_type, body.to_id))
    return {"ok": True}


@router.delete("/library/links/{link_id}")
async def library_unlink(link_id: int, db: AsyncSession = Depends(get_db)):
    await lib.unlink(db, link_id)
    return {"ok": True}


@router.get("/library/items/{item_id}/file")
async def library_file(
    item_id: int, size: Literal["small", "large", "original"] = "small", db: AsyncSession = Depends(get_db)
):
    try:
        item = await lib.get_item_model(db, item_id)
    except lib.LibraryNotFoundError as exc:
        raise _bad(exc, 404) from exc
    rel = (
        {"small": item.thumb_small, "large": item.thumb_large, "original": item.file_path}[size]
        or item.thumb_small
        or item.file_path
    )
    if not rel:
        raise HTTPException(status_code=404, detail="没有文件")
    try:
        path = abs_path(rel)
    except LibraryFileError as exc:
        raise _bad(exc, 404) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = "image/webp" if rel.endswith(".webp") else (item.mime or None)
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=86400"})


# ── 浏览器扩展 ──


class ExtensionBody(BaseModel):
    type: Literal["image", "link", "text"]
    url: str | None = Field(None, max_length=2048)  # 图片地址或网页地址
    page_url: str | None = Field(None, max_length=2048)
    page_title: str | None = Field(None, max_length=500)
    text: str | None = Field(None, max_length=20000)


@router.post("/library/extension/save")
async def extension_save(body: ExtensionBody, db: AsyncSession = Depends(get_db)):
    """右键「存到灵感库」：图片、链接、选中文字。"""
    import httpx

    try:
        if body.type == "link":
            item = await lib.add_from_link(db, body.url or body.page_url or "", method="extension")
        elif body.type == "text":
            item = await lib.add_text(
                db, body.text or "", kind="prompt", title=body.page_title, source_url=body.page_url, method="extension"
            )
        else:
            if not body.url:
                raise lib.LibraryError("缺少图片地址")
            async with httpx.AsyncClient(
                timeout=20, follow_redirects=True, headers={"User-Agent": lib.UA, "Referer": body.page_url or ""}
            ) as client:
                r = await client.get(body.url)
            if r.status_code >= 400:
                raise lib.LibraryError(f"取图失败：HTTP {r.status_code}")
            name = body.url.split("?")[0].rsplit("/", 1)[-1] or "image.jpg"
            item = await lib.add_file(
                db,
                r.content,
                name,
                mime=r.headers.get("content-type"),
                method="extension",
                title=body.page_title,
                source_url=body.page_url,
            )
    except lib.LibraryError as exc:
        raise _bad(exc) from exc
    return {"ok": True, "item": lib.item_view(item)}


@router.get("/library/extension/ping")
async def extension_ping():
    return {"ok": True, "app": "creative-workbench"}


# ── 画板 ──


class BoardBody(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = Field(None, max_length=2000)


class BoardItemsBody(BaseModel):
    item_ids: list[int] = Field(..., min_length=1, max_length=500)


@router.get("/library/boards")
async def boards(db: AsyncSession = Depends(get_db)):
    return {"items": await lib.list_boards(db)}


@router.post("/library/boards")
async def board_create(body: BoardBody, db: AsyncSession = Depends(get_db)):
    try:
        b = await lib.create_board(db, body.name, body.description)
    except lib.LibraryError as exc:
        raise _bad(exc) from exc
    return {"id": b.id, "name": b.name}


@router.post("/library/boards/{board_id}/items")
async def board_add(board_id: int, body: BoardItemsBody, db: AsyncSession = Depends(get_db)):
    try:
        return {"added": await lib.add_to_board(db, board_id, body.item_ids)}
    except lib.LibraryNotFoundError as exc:
        raise _bad(exc, 404) from exc


@router.delete("/library/boards/{board_id}/items/{item_id}")
async def board_remove(board_id: int, item_id: int, db: AsyncSession = Depends(get_db)):
    await lib.remove_from_board(db, board_id, item_id)
    return {"ok": True}


@router.delete("/library/boards/{board_id}")
async def board_delete(board_id: int, db: AsyncSession = Depends(get_db)):
    await lib.delete_board(db, board_id)
    return {"ok": True}


# ── 收件箱与迁移 ──


class InboxBody(BaseModel):
    path: str | None = Field(None, max_length=1024)


@router.get("/library/inbox")
async def inbox_get(db: AsyncSession = Depends(get_db)):
    p = await migration.inbox_dir(db)
    return {"path": str(p) if p else None, "imported_dir": migration.IMPORTED_DIR}


@router.put("/library/inbox")
async def inbox_put(body: InboxBody, db: AsyncSession = Depends(get_db)):
    try:
        return {"path": await migration.set_inbox_dir(db, body.path)}
    except OSError as exc:
        raise _bad(exc) from exc


@router.post("/library/inbox/scan")
async def inbox_scan(db: AsyncSession = Depends(get_db)):
    return await migration.scan_inbox(db)


@router.post("/library/migrate-favorites")
async def migrate_favorites(db: AsyncSession = Depends(get_db)):
    return await migration.migrate_favorites(db)


# ── 随笔 ──


class NoteBody(BaseModel):
    body: str = Field("", max_length=50000)
    image_item_ids: list[int] | None = None
    source: Literal["app", "tray"] = "app"


class NotePatch(BaseModel):
    body: str = Field(..., max_length=50000)


@router.get("/notes")
async def notes_list(
    tag: str | None = Query(None, max_length=60),
    q: str | None = Query(None, max_length=200),
    linked_type: str | None = Query(None, max_length=16),
    linked_id: int | None = None,
    before: date | None = None,
    days: int = Query(14, ge=1, le=120),
    db: AsyncSession = Depends(get_db),
):
    linked = (linked_type, linked_id) if linked_type and linked_id else None
    return await notes_svc.list_notes(db, tag=tag, q=q, linked=linked, before=before, days=days)


@router.post("/notes")
async def notes_create(body: NoteBody, db: AsyncSession = Depends(get_db)):
    try:
        note = await notes_svc.create_note(db, body.body, source=body.source, image_ids=body.image_item_ids)
    except notes_svc.NoteError as exc:
        raise _bad(exc) from exc
    related = await notes_svc.related_for_note(db, note)
    return {**notes_svc.note_view(note), "related": related}


@router.patch("/notes/{note_id}")
async def notes_update(note_id: int, body: NotePatch, db: AsyncSession = Depends(get_db)):
    try:
        note = await notes_svc.update_note(db, note_id, body.body)
    except LookupError as exc:
        raise _bad(exc, 404) from exc
    return notes_svc.note_view(note)


@router.delete("/notes/{note_id}")
async def notes_delete(note_id: int, db: AsyncSession = Depends(get_db)):
    await notes_svc.delete_note(db, note_id)
    return {"ok": True}


@router.post("/notes/{note_id}/audio")
async def notes_audio(note_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    data = await file.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="录音不得超过 50 MB")
    try:
        note = await notes_svc.attach_audio(db, note_id, data, file.filename or "voice.webm")
    except LookupError as exc:
        raise _bad(exc, 404) from exc
    try:
        note = await notes_svc.transcribe(db, note_id)
    except notes_svc.NoteError as exc:
        return {**notes_svc.note_view(note), "transcript_error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — 转写失败不丢录音
        return {**notes_svc.note_view(note), "transcript_error": f"转写失败：{exc}"[:300]}
    return notes_svc.note_view(note)


@router.post("/notes/images")
async def notes_image(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    data = await file.read(MAX_UPLOAD + 1)
    try:
        item = await notes_svc.add_note_image(db, data, file.filename or "paste.png", file.content_type)
    except lib.LibraryError as exc:
        raise _bad(exc) from exc
    return lib.item_view(item)


# ── 风格与模板 ──


class TemplateBody(BaseModel):
    name: str = Field(..., max_length=200)
    purpose: str | None = None
    audience: str | None = None
    structure: list[dict[str, Any]] | None = None
    tone: str | None = None
    reference_snippets: list[dict[str, Any]] | None = None
    forms: list[str] | None = None
    recommended_style_key: str | None = None
    cover_item_id: int | None = None
    note: str | None = None


class StyleBody(BaseModel):
    name: str = Field(..., max_length=200)
    palette: list[dict[str, Any]] | None = None
    fonts: list[dict[str, Any]] | None = None
    layout_rules: str | None = None
    motion_rules: str | None = None
    reference_item_ids: list[int] | None = None
    forms: list[str] | None = None
    note: str | None = None


class DistillBody(BaseModel):
    name: str = Field(..., max_length=200)
    item_ids: list[int] | None = None


@router.get("/templates")
async def templates_list(mine: bool = False, db: AsyncSession = Depends(get_db)):
    return {"items": await styles_svc.list_templates(db, include_builtin=not mine)}


@router.post("/templates")
async def templates_create(body: TemplateBody, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.create_template(db, body.name, body.model_dump(exclude={"name"}))
    except styles_svc.StyleError as exc:
        raise _bad(exc) from exc


@router.post("/templates/distill")
async def templates_distill(body: DistillBody, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.distill(db, "template", body.name, body.item_ids)
    except styles_svc.StyleError as exc:
        raise _bad(exc) from exc


@router.get("/templates/{key}")
async def templates_get(key: str, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.get_template(db, key)
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc


@router.post("/templates/{key}/versions")
async def templates_version(key: str, body: TemplateBody, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.add_template_version(db, key, body.model_dump(exclude_none=True))
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc


@router.post("/templates/{key}/copy")
async def templates_copy(key: str, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.copy_entry(db, "template", key)
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc


@router.delete("/templates/{key}")
async def templates_archive(key: str, db: AsyncSession = Depends(get_db)):
    try:
        await styles_svc.archive_entry(db, "template", key)
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc
    except styles_svc.StyleError as exc:
        raise _bad(exc) from exc
    return {"ok": True}


@router.get("/styles")
async def styles_list(mine: bool = False, db: AsyncSession = Depends(get_db)):
    return {"items": await styles_svc.list_styles(db, include_builtin=not mine)}


@router.post("/styles")
async def styles_create(body: StyleBody, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.create_style(db, body.name, body.model_dump(exclude={"name"}))
    except styles_svc.StyleError as exc:
        raise _bad(exc) from exc


@router.post("/styles/distill")
async def styles_distill(body: DistillBody, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.distill(db, "style", body.name, body.item_ids)
    except styles_svc.StyleError as exc:
        raise _bad(exc) from exc


@router.get("/styles/{key}")
async def styles_get(key: str, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.get_style(db, key)
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc


@router.post("/styles/{key}/versions")
async def styles_version(key: str, body: StyleBody, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.add_style_version(db, key, body.model_dump(exclude_none=True))
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc
    except styles_svc.StyleError as exc:
        raise _bad(exc) from exc


@router.post("/styles/{key}/copy")
async def styles_copy(key: str, db: AsyncSession = Depends(get_db)):
    try:
        return await styles_svc.copy_entry(db, "style", key)
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc


@router.delete("/styles/{key}")
async def styles_archive(key: str, db: AsyncSession = Depends(get_db)):
    try:
        await styles_svc.archive_entry(db, "style", key)
    except styles_svc.StyleNotFoundError as exc:
        raise _bad(exc, 404) from exc
    except styles_svc.StyleError as exc:
        raise _bad(exc) from exc
    return {"ok": True}
