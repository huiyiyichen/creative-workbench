"""专题（5.5）与选题结论的人工更正（4.3「不对」）。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TopicDossier(Base):
    """一个话题从出现到现在的完整经过。

    来源：持续 3 天以上的事件自动成为专题（event）；每个追踪词一个专题（watch_term）；
    任何话题都可以点「关注」（manual 或把自动专题标为 followed）。
    未关注、30 天没有新内容的自动专题归档（archived_at），仍可搜索。
    """

    __tablename__ = "topic_dossiers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # event / watch_term / manual
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    event_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("content_event_groups.id", ondelete="SET NULL"), nullable=True
    )
    watch_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    query: Mapped[str | None] = mapped_column(String(255), nullable=True)  # manual：按标题关键词匹配
    followed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 5.3 状态
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index(
            "uq_topic_dossiers_event",
            "event_group_id",
            unique=True,
            postgresql_where=text("event_group_id IS NOT NULL"),
        ),
        Index(
            "uq_topic_dossiers_watch",
            "watch_source_id",
            unique=True,
            postgresql_where=text("watch_source_id IS NOT NULL"),
        ),
    )


class VerdictMark(Base):
    """「不对」：你把结论改成正确的。参与个性化排序和规则调参；设置 · 评分说明显示一致率。"""

    __tablename__ = "verdict_marks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    computed_verdict: Mapped[str] = mapped_column(String(10), nullable=False)
    user_verdict: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("content_id", name="uq_verdict_marks_content"),)


class PeriodReport(Base):
    """空档回看与任意时间段报告（5.4）。日报 / 周刊 / 月刊沿用各自的表。

    * ``gap``：连续 2 天以上没有采集，开机补采完成后自动生成，范围为空档期间；
    * ``range``：手动选起止日期。
    ``sections`` 为结构化内容（大事、升温 / 降温话题、追踪词变化、错过的「值得做」、收藏话题的后续、采集概况）；
    同一范围重新生成时 version + 1，旧版本保留。
    """

    __tablename__ = "period_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # gap / range
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD（含）
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD（含）
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DONE")
    sections: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    completeness: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_period_reports_kind_range", "kind", "start_date", "end_date"),)
