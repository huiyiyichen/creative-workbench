"""语音转写（6.4 随笔录音）：千问（DashScope）OpenAI 兼容接口 ``/audio/transcriptions``。

用「AI 模型」里已经配置的 DashScope / 千问模型的 Key 和地址；没有配置时提示去设置。
转写模型可在 AppSetting ``speech_model`` 改（默认 ``qwen3-asr-flash``）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.llm_model import LlmModel
from app.services.secret_store import decrypt_secret

DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-asr-flash"


class SpeechNotConfigured(RuntimeError):
    pass


async def _config(db: AsyncSession) -> tuple[str, str, str]:
    model = (
        await db.execute(
            select(LlmModel)
            .where(
                LlmModel.api_key.is_not(None),
                or_(
                    LlmModel.provider.ilike("%dashscope%"),
                    LlmModel.provider.ilike("%qwen%"),
                    LlmModel.provider.ilike("%aliyun%"),
                    LlmModel.api_base.ilike("%dashscope%"),
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if model is None:
        raise SpeechNotConfigured("语音转写需要千问（DashScope）的 Key：在「设置 · AI 模型」添加一个千问模型后再试")
    key = decrypt_secret(model.api_key) or ""
    base = (model.api_base or DEFAULT_BASE).rstrip("/")
    row = await db.get(AppSetting, "speech_model")
    return base, key, (row.value if row and row.value else DEFAULT_MODEL)


async def transcribe_file(db: AsyncSession, path: Path) -> str:
    base, key, model = await _config(db)
    async with httpx.AsyncClient(timeout=120) as client:
        with path.open("rb") as fh:
            r = await client.post(
                f"{base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data={"model": model},
                files={"file": (path.name, fh)},
            )
    if r.status_code >= 400:
        raise RuntimeError(f"转写失败：HTTP {r.status_code} {r.text[:200]}")
    data = r.json()
    return str(data.get("text") or "")
