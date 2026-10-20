"""生图服务（创作工作台设计 6.5，方案第 8 节）。占位：阶段 4 第 ④ 步实现。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def available(db: AsyncSession) -> bool:
    return False


async def keyframe_for_flow(db: AsyncSession, **kw) -> int | None:
    return None
