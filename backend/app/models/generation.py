"""生成服务与生成任务（改造方案第 8 节、创作工作台设计 6.5）。"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GenerationService(Base):
    """设置 · 生成服务：名称、类型、接口格式、地址、Key（本地加密）、模型、能力、单价、每日上限。"""

    __tablename__ = "generation_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16), default="image")  # image / video / music
    api_format: Mapped[str] = mapped_column(String(32), default="openai_images")
    base_url: Mapped[str] = mapped_column(String(500))
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(100))
    # {"refs": bool 是否支持参考图, "sizes": {"1:1": "1024x1024", ...}, "max_n": 4}
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)  # 元 / 张
    daily_limit: Mapped[float | None] = mapped_column(Float, nullable=True)  # 元 / 天，空为不限
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class GenerationJob(Base):
    """一次生成：候选逐张落盘；选中的存入灵感库（kept）。没选中的候选保留 7 天。"""

    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="image")
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("generation_services.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    ref_item_ids: Mapped[list] = mapped_column(JSON, default=list)
    params: Mapped[dict] = mapped_column(JSON, default=dict)  # size / aspect / n / parent_job / ...
    target: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"type": "shot", "shot": 2} 等
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    output_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued / running / done / failed
    # [{"index": 0, "file": "data/generations/12/0.png", "library_item_id": null}]
    results: Mapped[list] = mapped_column(JSON, default=list)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
