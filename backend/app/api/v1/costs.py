"""花费总览接口。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.services.cost_service import cost_summary

router = APIRouter(prefix="/costs", tags=["costs"], dependencies=[Depends(get_current_user)])


@router.get("/summary")
async def costs_summary(days: int = Query(30, ge=1, le=180), db: AsyncSession = Depends(get_db)):
    return await cost_summary(db, days=days)
