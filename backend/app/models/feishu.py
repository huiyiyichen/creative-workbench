"""飞书多维表格同步记录（改造方案 10.2）：工作台对象 → 飞书表格里的一条记录。"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeishuRecord(Base):
    __tablename__ = "feishu_records"
    __table_args__ = (UniqueConstraint("object_type", "object_id", "table_id", name="uq_feishu_records_object_table"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(16))  # content / project
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    app_token: Mapped[str] = mapped_column(String(64))
    table_id: Mapped[str] = mapped_column(String(64))
    record_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / synced / failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual / auto / stage
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
