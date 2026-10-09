"""Receive a local credential through stdin and store it encrypted."""

import asyncio
import getpass
import json

from app.core.database import async_session
from app.services.studio_tts import TtsSettings, save_tts_config


async def main():
    request = TtsSettings(api_key=getpass.getpass("TTS key: "))
    async with async_session() as db:
        result = await save_tts_config(db, request)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(main())
