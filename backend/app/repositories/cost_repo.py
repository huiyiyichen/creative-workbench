"""花费汇总的查询：LLM 调用（按场景 / 模型 / 项目 / 天）与生成任务（按种类 / 服务 / 项目 / 天）。

LLM 的花费以 llm_call_logs.total_cost 为准；agent 运行与步骤上的 cost 是同一批调用的汇总，
不能再加一遍，所以这里只把 agent_runs 当作「按运行看」的维度。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation import GenerationJob, GenerationService
from app.models.llm_model import LlmCallLog


class CostRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _cn_day(self, col):
        """北京时间的日期。PostgreSQL 用 timezone()，SQLite（单测）用固定 +8 小时。"""
        if self.db.bind.dialect.name == "sqlite":
            return func.date(col, "+8 hours")
        return func.date(func.timezone("Asia/Shanghai", col))

    async def llm_groups(self, start: datetime, end: datetime) -> list[tuple]:
        """按（北京时间日期, 场景, 模型, 项目）聚合：(day, scene, model, project_id, cost, calls, in_tok, out_tok, failed)"""
        day = self._cn_day(LlmCallLog.created_at)
        model = func.coalesce(LlmCallLog.model_name, LlmCallLog.request_model)
        stmt = (
            select(
                day,
                LlmCallLog.scene,
                model,
                LlmCallLog.project_id,
                func.coalesce(func.sum(LlmCallLog.total_cost), 0.0),
                func.count(),
                func.coalesce(func.sum(LlmCallLog.input_tokens), 0),
                func.coalesce(func.sum(LlmCallLog.output_tokens), 0),
                func.count().filter(LlmCallLog.status != "DONE"),
            )
            .where(LlmCallLog.created_at >= start, LlmCallLog.created_at < end)
            .group_by(day, LlmCallLog.scene, model, LlmCallLog.project_id)
        )
        return list((await self.db.execute(stmt)).all())

    async def generation_groups(self, start: datetime, end: datetime) -> list[tuple]:
        """按（日期, 种类, 服务, 项目）聚合：(day, kind, service_name, project_id, cost, jobs, failed)"""
        day = self._cn_day(GenerationJob.created_at)
        stmt = (
            select(
                day,
                GenerationJob.kind,
                GenerationService.name,
                GenerationJob.project_id,
                func.coalesce(func.sum(GenerationJob.cost), 0.0),
                func.count(),
                func.count().filter(GenerationJob.status == "failed"),
            )
            .outerjoin(GenerationService, GenerationService.id == GenerationJob.service_id)
            .where(GenerationJob.created_at >= start, GenerationJob.created_at < end)
            .group_by(day, GenerationJob.kind, GenerationService.name, GenerationJob.project_id)
        )
        return list((await self.db.execute(stmt)).all())

    async def project_titles(self, ids: list[int]) -> dict[int, str]:
        if not ids:
            return {}
        from app.models.project import Project

        rows = (await self.db.execute(select(Project.id, Project.title).where(Project.id.in_(ids)))).all()
        return {int(i): t for i, t in rows}
