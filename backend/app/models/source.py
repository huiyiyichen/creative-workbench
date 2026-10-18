from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enum_types import value_enum

if TYPE_CHECKING:
    from app.models.content import ContentItem


class SourceType(enum.StrEnum):
    RSS = "RSS"
    RSSHub = "RSSHub"
    REDDIT = "Reddit"
    WEBSITE = "网站"
    X = "X"
    TWITTER_RSS = "TwitterRSS"
    YOUTUBE = "YouTube"
    PODCAST = "Podcast"
    NEWSLETTER = "Newsletter"
    ZHIHU = "Zhihu"
    DOUYIN_HOT = "DouyinHot"
    API = "API"
    # 阶段 1 平台适配器（3.2）：订阅 / 榜单走 PLATFORM，追踪词走 KEYWORD
    PLATFORM = "Platform"
    KEYWORD = "Keyword"


class SourceKind(enum.StrEnum):
    """三类信源（改造方案 3.1）。"""

    SUBSCRIPTION = "subscription"  # 订阅：跟踪账号 / 频道 / 仓库 / RSS
    KEYWORD = "keyword"  # 追踪词：一个词同时在多个平台搜索
    LIST = "list"  # 榜单：平台热榜


class SourceStatus(enum.StrEnum):
    ACTIVE = "active"
    SYNCING = "syncing"
    ERROR = "error"
    DISABLED = "disabled"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SourceKind.SUBSCRIPTION.value, server_default="subscription"
    )
    # 追踪词：搜索词与要搜的平台列表（如 ["bilibili", "youtube", "github", "hn"]）
    query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platforms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(value_enum(SourceType), nullable=False, default=SourceType.RSS)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(value_enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── Conditional request state (HTTP If-None-Match / If-Modified-Since) ──
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ── 自动处理（3.9）：与用户的 enabled 开关分开，撤销即清空 ──
    auto_paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_pause_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # 限流退避前的原间隔；为空表示当前没有退避
    base_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stale_flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    hidden: Mapped[bool] = mapped_column(default=False, comment="True=系统自动创建的信源，对用户不可见且不计入配额")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_sources_owner", "owner_user_id"),
        Index("ix_sources_owner_enabled", "owner_user_id", "enabled"),
    )

    contents: Mapped[list[ContentItem]] = relationship(back_populates="source", cascade="all, delete-orphan")
