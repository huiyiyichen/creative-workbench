"""Local workspace identity helpers.

The application has one local owner. Account registration, sessions, API
tokens, passwords and OAuth are intentionally outside the runtime model.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole

LOCAL_USER_EMAIL = "local@topiceye.local"
LOCAL_USER_NAME = "本地创作者"


async def get_local_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).order_by(User.id.asc()).limit(1))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        email=LOCAL_USER_EMAIL,
        display_name=LOCAL_USER_NAME,
        plan="local",
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
