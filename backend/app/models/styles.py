"""风格与模板（改造方案 6.6）。

风格写成色板、字体、版式、动效规则；模板写成结构、语气。版本一经创建不可修改，编辑即新版本；
工程固定引用版本。内置的作为种子数据按 ``key`` 幂等写入（``builtin=True``），编辑内置时复制成自定义。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContentTemplate(Base):
    __tablename__ = "content_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    copied_from: Mapped[str | None] = mapped_column(String(100), nullable=True)
    legacy_favorite_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class ContentTemplateVersion(Base):
    __tablename__ = "content_template_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_templates.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)  # 用途
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)  # 受众
    structure: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)  # 段落与要点
    tone: Mapped[str | None] = mapped_column(Text, nullable=True)  # 语气
    reference_snippets: Mapped[list | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )  # 参考片段（可关联采集内容）
    forms: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)  # 适用形态
    recommended_style_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cover_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 这一版改了什么
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_template_version"),)


class VisualStyle(Base):
    __tablename__ = "visual_styles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    copied_from: Mapped[str | None] = mapped_column(String(100), nullable=True)
    legacy_favorite_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class VisualStyleVersion(Base):
    __tablename__ = "visual_style_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    style_id: Mapped[int] = mapped_column(Integer, ForeignKey("visual_styles.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    palette: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)  # [{"name","hex"}]
    fonts: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)  # [{"role","family","item_id"}]
    layout_rules: Mapped[str | None] = mapped_column(Text, nullable=True)  # 版式与构图
    motion_rules: Mapped[str | None] = mapped_column(Text, nullable=True)  # 动效
    reference_item_ids: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)  # 参考图（灵感库）
    forms: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("style_id", "version", name="uq_style_version"),)
