"""每次信源同步一行记录（改造方案 3.3 / 3.8）。

采集页的健康、成功率、最近失败原因、每日新增都从这张表计算；
自动处理（3.9）根据最近几次运行判断是否暂停信源。
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncRunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    EMPTY = "empty"  # 成功但 0 条
    FAILED = "failed"
    SKIPPED = "skipped"  # 被暂停 / 不支持等原因未实际抓取


class SyncErrorKind(enum.StrEnum):
    LOGIN = "login"  # 登录失效
    CAPTCHA = "captcha"  # 出现验证码
    RATE_LIMIT = "rate_limit"  # 429 等限流
    TIMEOUT = "timeout"
    API_CHANGED = "api_changed"  # 接口变化 / 解析失败
    BLOCKED = "blocked"  # SSRF 拦截、403
    OTHER = "other"


class SyncTrigger(enum.StrEnum):
    SCHEDULE = "schedule"
    MANUAL = "manual"
    STARTUP = "startup"  # 启动时补采
    RETRY = "retry"  # 自动暂停后的定期重试


class SourceSyncRun(Base):
    __tablename__ = "source_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default=SyncTrigger.SCHEDULE.value)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SyncRunStatus.RUNNING.value)
    error_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicates: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skipped: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="预筛跳过，按原因计数")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_backfill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_source_sync_runs_source_started", "source_id", "started_at"),
        Index("ix_source_sync_runs_started", "started_at"),
    )
