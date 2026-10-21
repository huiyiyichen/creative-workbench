"""向供应商 / 中转站接口拉取「这把 Key 实际能用的模型」。

models.dev 目录只是参考：中转站常改名、按分组开放模型（例如「deepseek-flash 在此分组不可用」），
所以模型名应以接口 ``GET {api_base}/models`` 的返回为准。
"""

from __future__ import annotations

from typing import Any

import httpx

# 没填 API Base 时按 provider 兜底的官方地址（OpenAI 兼容 /models）
DEFAULT_BASES: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "openrouter": "https://openrouter.ai/api/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "xai": "https://api.x.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class RemoteModelsError(Exception):
    pass


def resolve_base(api_base: str | None, provider: str | None, api_format: str) -> str:
    base = (api_base or "").strip().rstrip("/")
    if base:
        return base
    if api_format == "gemini" or (provider or "") == "gemini":
        return GEMINI_BASE
    fallback = DEFAULT_BASES.get((provider or "").strip().lower())
    if not fallback:
        raise RemoteModelsError("请先填写 API Base URL（中转站一般是 /v1 结尾的地址）")
    return fallback


def parse_models(payload: Any) -> list[dict[str, str | None]]:
    """兼容 OpenAI ``{"data":[{"id"}]}``、Gemini ``{"models":[{"name":"models/x"}]}`` 和裸数组。"""
    rows: list[Any]
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("models") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    out: dict[str, dict[str, str | None]] = {}
    for row in rows:
        if isinstance(row, str):
            mid, owner = row, None
        elif isinstance(row, dict):
            mid = str(row.get("id") or row.get("name") or "").strip()
            owner = row.get("owned_by") or row.get("displayName")
        else:
            continue
        mid = mid.removeprefix("models/")
        if mid and mid not in out:
            out[mid] = {"id": mid, "owned_by": str(owner) if owner else None}
    return sorted(out.values(), key=lambda r: str(r["id"]).lower())


async def list_remote_models(
    *, api_base: str | None, api_key: str | None, provider: str | None, api_format: str = "openai"
) -> dict[str, Any]:
    base = resolve_base(api_base, provider, api_format)
    gemini = api_format == "gemini" or base.startswith(GEMINI_BASE)
    url = f"{base}/models"
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    if api_key:
        if gemini:
            params["key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        raise RemoteModelsError(f"连不上 {url}：{exc.__class__.__name__}") from exc
    if resp.status_code in (401, 403):
        raise RemoteModelsError(f"接口拒绝了这把 Key（HTTP {resp.status_code}），检查 API Key 是否正确")
    if resp.status_code == 404:
        raise RemoteModelsError(f"{url} 不存在（404），API Base 可能少了 /v1")
    if resp.status_code >= 400:
        raise RemoteModelsError(f"接口返回 HTTP {resp.status_code}：{resp.text[:160]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise RemoteModelsError("接口返回的不是 JSON，API Base 可能填成了网页地址") from exc
    models = parse_models(payload)
    if not models:
        raise RemoteModelsError("接口没有返回任何模型")
    return {"source": url, "models": models, "total": len(models)}
