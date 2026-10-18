"""Local workspace identity helpers.

The application has one local owner. Account registration, sessions, API
tokens, passwords and OAuth are intentionally outside the runtime model.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole

LOCAL_USER_EMAIL = "local@creative-workbench.local"
LOCAL_USER_NAME = "本地创作者"


async def get_local_user(db: AsyncSession) -> User:
    """返回唯一的本地用户，并保证其为管理员、处于启用状态。

    旧库里 id 最小的用户可能不是管理员（问题清单 E2），这里就地修正；
    两个请求同时首次创建时，后提交的一方撞唯一约束后回滚重查（第 13 节 #4）。
    """
    user = await _first_user(db)
    if user is None:
        db.add(
            User(
                email=LOCAL_USER_EMAIL,
                display_name=LOCAL_USER_NAME,
                plan="local",
                role=UserRole.ADMIN.value,
                is_active=True,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
        user = await _first_user(db)
        if user is None:  # pragma: no cover - 只有数据库异常才会走到
            raise RuntimeError("无法创建本地用户")
    if user.role != UserRole.ADMIN.value or not user.is_active:
        user.role = UserRole.ADMIN.value
        user.is_active = True
        await db.commit()
        await db.refresh(user)
    return user


async def _first_user(db: AsyncSession) -> User | None:
    result = await db.execute(select(User).order_by(User.id.asc()).limit(1))
    return result.scalar_one_or_none()
