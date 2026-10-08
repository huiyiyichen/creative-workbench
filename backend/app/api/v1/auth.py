"""Local workspace identity.

Creative Workbench is a single-user application. There is no login, registration,
password, email verification, session or OAuth flow. The dependency remains
so personal-data endpoints can keep a stable owner.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import UserResponse
from app.services.auth_service import get_local_user

router = APIRouter(prefix="/auth", tags=["workspace"])


async def get_current_user(db: AsyncSession = Depends(get_db)) -> User:
    return await get_local_user(db)


async def get_optional_current_user(db: AsyncSession = Depends(get_db)) -> User:
    return await get_local_user(db)


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


def is_admin(user: User | None) -> bool:
    return bool(user and user.role == UserRole.ADMIN.value)


def require_admin_view(admin_view: bool, user: User | None) -> None:
    if admin_view and not is_admin(user):
        raise HTTPException(status_code=403, detail="Local workspace identity is unavailable")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
