from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enum_types import value_enum

if TYPE_CHECKING:
    from app.models.ai_analysis import AiAnalysis
    from app.models.article_snapshot import ArticleSnapshot
    from app.models.metrics import ContentMetrics
    from app.models.source import Source
    from app.models.topic import TopicGroup


class ContentStatus(enum.StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    ERROR = "error"


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="冗余 source.owner_user_id；NULL=公共内容池"
    )
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 内容形态（双轴分类的 format 轴）：论文/技术/资讯/教程/观点/工具/体验/成长/讨论/项目
    # 由 source.category 的 `/` 分隔符解析或 LLM 分类填充
    content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(value_enum(ContentStatus), nullable=False, default=ContentStatus.PENDING)
    is_favorited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # LLM 规则过滤层（参照 content-signal-radar 的 lowSignalPenalty 设计）
    # skip_analysis=True 时不进 LLM 队列（不入 claim_pending），但仍入库保留
    skip_analysis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    skip_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 持久化分析队列元数据：ERROR 仅在 next_retry_at 到期且未超过尝试上限时重试。
    analysis_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analysis_next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 每次领取都会生成新的 fencing token。只有持有当前 token 的 worker 才能
    # 写入最终状态，避免租约过期后的旧 worker 迟到覆盖新 worker 的结果。
    analysis_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── 内容模型（改造方案 3.3） ──
    # 形态：article / video / image / repo / prompt / post（content_type 继续存分类）
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    platform_item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # 时长（秒）、横竖屏（orientation）、视频地址、图片列表等
    media: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    cover_asset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    # 评论：none / collected / unavailable / failed
    comment_state: Mapped[str] = mapped_column(String(20), nullable=False, default="none", server_default="none")
    comment_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ── 分析漏斗（4.1） ──
    triage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    triage_signals: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # none / quick / full
    analysis_level: Mapped[str] = mapped_column(String(10), nullable=False, default="none", server_default="none")
    quick_result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # 快速判断结论：None=未判断，True=值得完整分析，False=不做完整分析
    full_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 归属日期（5.4 / 第 13 节 #17）：发布日期，缺发布时间按采集日期（Asia/Shanghai）
    attributed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 选题结论（4.3）：worth / watch / skip；verdict_data 为结论、理由、依据、缺失项、计算明细
    verdict: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    verdict_data: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Topic clustering fields
    topic_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("topic_groups.id", ondelete="SET NULL"), nullable=True
    )
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
        Index("ix_content_items_owner", "owner_user_id"),
        Index("ix_content_items_owner_status", "owner_user_id", "status"),
        Index("ix_content_items_crawled_at", crawled_at.desc()),
        Index("ix_content_items_status_crawled", "status", crawled_at.desc()),
        # list_all_by_topic_id() — WHERE topic_id = ? ORDER BY crawled_at DESC
        Index("ix_content_items_topic_id", "topic_id"),
        # source_health_repo — WHERE source_id = ? / GROUP BY source_id
        Index("ix_content_items_source_id", "source_id"),
        UniqueConstraint("source_id", "content_hash", name="uq_content_items_source_hash"),
        Index("ix_content_items_attributed_date", "attributed_date"),
        Index("ix_content_items_platform_item", "platform", "platform_item_id"),
        Index("ix_content_items_triage", "status", "triage_score"),
    )

    source: Mapped[Source | None] = relationship(back_populates="contents")
    metrics: Mapped[list[ContentMetrics]] = relationship(back_populates="content", cascade="all, delete-orphan")
    analyses: Mapped[list[AiAnalysis]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
        order_by="AiAnalysis.created_at, AiAnalysis.id",
    )
    topic: Mapped[TopicGroup | None] = relationship(back_populates="items", foreign_keys=[topic_id])
    reader_snapshot: Mapped[ArticleSnapshot | None] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
        uselist=False,
    )
