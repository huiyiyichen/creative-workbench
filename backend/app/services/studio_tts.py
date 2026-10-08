from __future__ import annotations

import asyncio
import base64
import io
import json
import wave
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.repositories.app_setting_repo import AppSettingRepository
from app.services.secret_store import decrypt_secret, encrypt_secret

SETTING_KEY = "studio_tts"
DEFAULTS = {
    "base_url": "https://maas.qianwenaiapi.com/compatible-mode/v1",
    "model": "qwen3.5-omni-flash",
    "voice": "Ethan",
}
_synthesis_lock = asyncio.Lock()


class TtsSettings(BaseModel):
    api_key: str | None = Field(default=None, max_length=1000)
    voice: str = Field(default="", max_length=200)


async def tts_config(db: AsyncSession, *, with_secret: bool = False) -> dict:
    row = await AppSettingRepository(db).get_by_key(SETTING_KEY)
    value = {**DEFAULTS, **(json.loads(row.value) if row else {})}
    if value.get("model", "").startswith("qwen-audio"):
        value["model"] = DEFAULTS["model"]
        value["voice"] = DEFAULTS["voice"]
    encrypted_key = value.pop("api_key", None)
    value["configured"] = bool(encrypted_key)
    if with_secret:
        value["api_key"] = decrypt_secret(encrypted_key)
    return value


async def save_tts_config(db: AsyncSession, request: TtsSettings) -> dict:
    repo = AppSettingRepository(db)
    row = await repo.get_by_key(SETTING_KEY)
    value = {**DEFAULTS, **(json.loads(row.value) if row else {})}
    if request.api_key:
        value["api_key"] = encrypt_secret(request.api_key)
    value["voice"] = request.voice.strip()
    await repo.upsert_setting(SETTING_KEY, json.dumps(value, ensure_ascii=False), existing=row)
    await db.commit()
    return await tts_config(db)


def _synthesize(text: str, config: dict) -> tuple[bytes, str]:
    endpoint = config["base_url"].rstrip("/") + "/chat/completions"
    audio_parts: list[str] = []
    spoken_parts: list[str] = []
    try:
        with (
            httpx.Client(timeout=120) as client,
            client.stream(
                "POST",
                endpoint,
                headers={
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config["model"],
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是中文配音员。完整逐字朗读用户提供的稿件，输出文本与稿件保持一致，声音清晰自然，按照标点停顿。",
                        },
                        {"role": "user", "content": text},
                    ],
                    "modalities": ["text", "audio"],
                    "audio": {"voice": config["voice"], "format": "wav"},
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            ) as response,
        ):
            if not response.is_success:
                detail = ""
                try:
                    response.read()
                    error = json.loads(response.text).get("error", {})
                    detail = str(error.get("code") or error.get("message") or "")
                except (ValueError, TypeError):
                    pass
                if detail == "AccessDenied.Unpurchased":
                    raise ValidationError("当前 Key 尚未开通 qwen3.5-omni-flash")
                raise ValidationError(f"Omni TTS 请求失败（HTTP {response.status_code}）")
            for line in response.iter_lines():
                if not line or not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                try:
                    payload = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                for choice in payload.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        spoken_parts.append(delta["content"])
                    encoded = (delta.get("audio") or {}).get("data")
                    if encoded:
                        audio_parts.append(encoded)
    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"Omni TTS 合成失败（{type(exc).__name__}）") from None
    if not audio_parts:
        raise ValidationError("Omni TTS 接口返回空音频")
    # Omni's streamed audio is 24 kHz mono PCM16, including format="wav".
    pcm = base64.b64decode("".join(audio_parts))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return output.getvalue(), "".join(spoken_parts)


async def synthesize_speech(text: str, config: dict, output: Path) -> Path:
    if not config.get("api_key"):
        raise ValidationError("请配置千问 TTS 密钥")
    async with _synthesis_lock:
        audio, spoken_text = await asyncio.to_thread(_synthesize, text, config)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)
    output.with_suffix(".txt").write_text(spoken_text, encoding="utf-8")
    return output
