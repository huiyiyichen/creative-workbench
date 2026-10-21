"""灵感库（改造方案 6）：条目、画板、关联、随笔。

* ``library_items``：所有收进来的东西。``kind`` 为条目类型（6.1），美术素材另有 ``asset_kind``。
  原文件存 ``data/library/``，按 sha256 去重，库里只记相对路径（6.3）。
* ``library_boards`` / ``library_board_items``：画板（6.5）。
* ``library_links``：关联（6.7）。两端用 ``(类型, id)`` 表示，类型为 item / note / content / dossier / project。
* ``notes``：随笔（6.4）；Obsidian 中每条随笔是当天文件里带 ``^cw-<id>`` 锚点的小节。
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LibraryKind(enum.StrEnum):
    ARTICLE = "article"
    VIDEO = "video"
    IMAGE_TEXT = "image"  # 图文
    POST = "post"
    PROMPT = "prompt"
    REPO = "repo"
    ASSET = "asset"  # 美术素材，细分见 asset_kind
    GENERATED = "generated"  # 生成图
    LINK = "link"


class AssetKind(enum.StrEnum):
    IMAGE = "image"  # 照片、插画、海报、截图
    PALETTE = "palette"
    FONT = "font"
    ICON = "icon"  # 图标与贴纸
    TEXTURE = "texture"
    MOTION = "motion"  # 动图与视频片段
    AUDIO = "audio"  # 音乐与音效


class License(enum.StrEnum):
    OWN = "own"  # 自有
    COMMERCIAL = "commercial"  # 可商用
    REFERENCE = "reference"  # 仅参考
    UNKNOWN = "unknown"
    AI = "ai"  # AI 生成


LICENSE_LABEL = {"own": "自有", "commercial": "可商用", "reference": "仅参考", "unknown": "未知", "ai": "AI 生成"}


class ImportMethod(enum.StrEnum):
    FAVORITE = "favorite"  # 一键收藏
    LINK = "link"  # 粘贴链接
    EXTENSION = "extension"  # 浏览器扩展
    CLIPBOARD = "clipboard"
    FILE = "file"  # 本地文件
    INBOX = "inbox"  # 素材收件箱
    FRAME = "frame"  # 从内容取图 / 视频截帧
    GENERATED = "generated"
    EXTRACTED = "extracted"  # 从视频描述 / 网页中提取的提示词、仓库
    MIGRATED = "migrated"  # 旧收藏夹迁移
    OBSIDIAN = "obsidian"
    BREAKDOWN = "breakdown"  # 爆款拆解时收进来


class LibraryItem(Base):
    __tablename__ = "library_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True
    )
    # 正文：提示词正文、README 摘要、选中文字、网页摘要
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 类型相关的结构化字段：提示词变量 / 适用模型 / 示例；仓库 Star / 语言 / 最近发布；生成参数；字体名与字重 …
    meta: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # 文件（6.3）
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumb_small: Mapped[str | None] = mapped_column(String(512), nullable=True)  # 320px WebP
    thumb_large: Mapped[str | None] = mapped_column(String(512), nullable=True)  # 960px WebP
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(nullable=True)
    dominant_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    palette: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    license: Mapped[str] = mapped_column(String(16), nullable=False, default=License.UNKNOWN.value)
    import_method: Mapped[str] = mapped_column(String(16), nullable=False, default=ImportMethod.FAVORITE.value)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    ai_tags: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    ai_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    my_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Obsidian「我的笔记」读回
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    obsidian_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    legacy_favorite_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_library_items_kind_created", "kind", "created_at"),
        Index("ix_library_items_sha", "file_sha256"),
        Index("ix_library_items_content", "content_id"),
        Index("ix_library_items_url", "url"),
    )


class LibraryBoard(Base):
    __tablename__ = "library_boards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class LibraryBoardItem(Base):
    __tablename__ = "library_board_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    board_id: Mapped[int] = mapped_column(Integer, ForeignKey("library_boards.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("library_items.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("board_id", "item_id", name="uq_board_item"),)


class LinkRelation(enum.StrEnum):
    SAME_EVENT = "same_event"
    SAME_TAG = "same_tag"
    SAME_AUTHOR = "same_author"
    SIMILAR = "similar"
    USED_IN_PROJECT = "used_in_project"
    DISTILLED = "distilled"  # 素材 → 风格 / 模板
    GENERATED = "generated"  # 提示词 / 参考图 → 生成图
    EXTRACTED = "extracted"  # 原内容 → 提取出的提示词 / 仓库
    WIKILINK = "wikilink"  # 你写的 [[双链]]
    MANUAL = "manual"


class LibraryLink(Base):
    __tablename__ = "library_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_type: Mapped[str] = mapped_column(String(16), nullable=False)
    from_id: Mapped[int] = mapped_column(Integer, nullable=False)
    to_type: Mapped[str] = mapped_column(String(16), nullable=False)
    to_id: Mapped[int] = mapped_column(Integer, nullable=False)
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("from_type", "from_id", "to_type", "to_id", "relation", name="uq_library_link"),
        Index("ix_library_links_to", "to_type", "to_id"),
    )


class Note(Base):
    """随笔（6.4）。"""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_item_ids: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    transcript_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # pending / done / failed
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="app")  # app / tray / obsidian
    obsidian_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_notes_created", "created_at"),)
