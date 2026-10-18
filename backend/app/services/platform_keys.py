"""平台 API Key（YouTube Data API、GitHub Token）。加密存 AppSetting，环境变量兜底。"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.app_setting_repo import AppSettingRepository
from app.services.platforms import KEY_ENV
from app.services.secret_store import decrypt_secret, encrypt_secret


def _key_name(platform: str) -> str:
    return f"platform_key_{platform}"


async def get_platform_keys(db: AsyncSession) -> dict[str, str]:
    repo = AppSettingRepository(db)
    out: dict[str, str] = {}
    for platform, env in KEY_ENV.items():
        row = await repo.get_by_key(_key_name(platform))
        value = decrypt_secret(row.value) if row and row.value else None
        value = value or os.environ.get(env)
        if value:
            out[platform] = value
    return out


async def set_platform_key(db: AsyncSession, platform: str, value: str | None) -> None:
    if platform not in KEY_ENV:
        raise ValueError(f"{platform} 不需要 API Key")
    await AppSettingRepository(db).upsert_setting(_key_name(platform), encrypt_secret(value) if value else "")
    await db.commit()


async def key_status(db: AsyncSession) -> dict[str, bool]:
    keys = await get_platform_keys(db)
    return {platform: platform in keys for platform in KEY_ENV}
