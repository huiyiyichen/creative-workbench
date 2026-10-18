from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.content import ContentItem


class ContentMetrics(Base):
    """采集时的平台指标快照。缺失保持 NULL，不记 0（改造方案 3.3）。"""

    __tablename__ = "content_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favorites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    explosion_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    content: Mapped[ContentItem] = relationship(back_populates="metrics")

    __table_args__ = (
        # selectinload(ContentItem.metrics) — WHERE content_id IN (...)
        Index("ix_content_metrics_content_id", "content_id"),
    )
