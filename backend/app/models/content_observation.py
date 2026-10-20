"""内容指标观测、封面缓存、内容经历（改造方案 3.3 / 3.4 / 2.3）。"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetricName(enum.StrEnum):
    VIEWS = "views"  # 播放 / 阅读
    LIKES = "likes"
    COMMENTS = "comments"
    FAVORITES = "favorites"  # 收藏
    SHARES = "shares"  # 转发
    COINS = "coins"  # B站投币
    DANMAKU = "danmaku"
    STARS = "stars"  # GitHub Star
    FORKS = "forks"
    SCORE = "score"  # HN / Reddit 分数
    HOT = "hot"  # 热度值
    RANK = "rank"  # 榜单排名


class ContentMetricObservation(Base):
    """一次观测一行；没有观测就没有记录，界面显示「暂无历史观测」。"""

    __tablename__ = "content_metric_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    metric: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    sync_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("source_sync_runs.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_metric_obs_content_metric_time", "content_id", "metric", "observed_at"),
        Index("ix_metric_obs_observed", "observed_at"),
    )


class MediaAssetStatus(enum.StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class MediaAsset(Base):
    """封面与图片的本地缓存（3.4）。"""

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumb_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dominant_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=MediaAssetStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pinned: Mapped[bool] = mapped_column(default=False, comment="被收藏或项目引用：清理时永久保留")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("url_hash", name="uq_media_assets_url_hash"),
        Index("ix_media_assets_status", "status"),
        Index("ix_media_assets_last_accessed", "last_accessed_at"),
    )


class JourneyStage(enum.StrEnum):
    COLLECTED = "collected"  # 采集
    PREFILTER = "prefilter"  # 预筛
    TRIAGE = "triage"  # 初筛
    EVENT = "event"  # 归并
    QUICK = "quick"  # 快速判断
    FULL = "full"  # 完整分析
    VERDICT = "verdict"  # 结论
    FAVORITED = "favorited"
    USED_IN_PROJECT = "used_in_project"
    IN_WORK = "in_work"  # 进入成片


class ContentJourney(Base):
    """内容经历：每条内容从采集到成片的每一步（2.3）。"""

    __tablename__ = "content_journey"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sync_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_content_journey_content_time", "content_id", "created_at"),)


class ContentEmbedding(Base):
    """本地向量（4.1 事件归并、初筛「与收藏的相似度」）。float32 L2 归一化。"""

    __tablename__ = "content_embeddings"

    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_content_embeddings_created", "created_at"),)


__all__ = [
    "ContentEmbedding",
    "ContentJourney",
    "ContentMetricObservation",
    "JourneyStage",
    "MediaAsset",
    "MediaAssetStatus",
    "MetricName",
]


class ContentComment(Base):
    """条目评论（3.5）：热门前 20 条，不取回复；只存昵称与文本。随内容删除。"""

    __tablename__ = "content_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_comment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    author_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("platform", "platform_comment_id", name="uq_content_comment"),
        Index("ix_content_comments_content", "content_id"),
    )
