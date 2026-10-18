"""自动处理记录（改造方案 3.9）。

能撤销、只起保护作用的动作由系统自动执行（暂停失败信源、限流退避、
标记可能失效），每一条都写在这里；撤销即按 ``previous_state`` 恢复原状态。
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AutoActionType(enum.StrEnum):
    PAUSE_SOURCE = "pause_source"  # 连续失败 3 次
    PAUSE_PLATFORM = "pause_platform"  # 登录失效 / 验证码
    BACKOFF_SOURCE = "backoff_source"  # 限流，间隔翻倍
    FLAG_STALE = "flag_stale"  # 超过平常间隔 3 倍没有新内容
    RESUME_SOURCE = "resume_source"  # 暂停后重试成功，自动恢复


class AutoAction(Base):
    __tablename__ = "auto_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, default="source")  # source / platform
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_auto_actions_executed", "executed_at"),
        Index("ix_auto_actions_target", "target_type", "target_id"),
    )


__all__ = ["AutoAction", "AutoActionType"]
