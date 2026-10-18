"""模型调用 / 工具调用的完整载荷存储（改造方案 2.3）。

载荷（完整提示词、回复、工具参数与结果）压缩后存 ``data/traces/YYYY/MM/DD/<id>.json.gz``，
数据库只存相对路径和摘要。写入前脱敏：API Key、Cookie、Authorization。
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services._error_redaction import redact_source_sync_error

logger = logging.getLogger(__name__)

TRACE_ROOT = Path(__file__).resolve().parents[2] / "data" / "traces"
_COOKIE_RE = re.compile(r"(?i)(\bcookie\b[\"']?\s*[:=]\s*[\"']?)([^\"'\n]+)")
_SK_RE = re.compile(r"\b(sk-[A-Za-z0-9_\-]{12,})\b")


def redact(text: str) -> str:
    if not text:
        return text
    out = redact_source_sync_error(text) if text.strip() else text
    out = _COOKIE_RE.sub(r"\1***", out)
    return _SK_RE.sub("sk-***", out)


def _redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redact_obj(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in {"api_key", "authorization", "cookie", "token", "password"}:
                out[k] = "***"
            else:
                out[k] = _redact_obj(v)
        return out
    return value


def summarize(text: str | None, limit: int = 280) -> str | None:
    if not text:
        return None
    flat = " ".join(redact(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def prompt_text(messages: list[dict[str, Any]] | None) -> str:
    """最后一条 user 消息，作为摘要来源。"""
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            content = msg.get("content")
            return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return ""


def save_payload(request_id: str, payload: dict[str, Any], *, root: Path | None = None) -> str | None:
    """压缩写入载荷，返回相对 traces 根目录的路径；失败返回 None（不影响主链路）。"""
    base = root or TRACE_ROOT
    now = datetime.now(UTC)
    rel = Path(f"{now:%Y/%m/%d}") / f"{request_id}.json.gz"
    try:
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(_redact_obj(payload), ensure_ascii=False, default=str).encode("utf-8")
        with gzip.open(path, "wb") as fh:
            fh.write(data)
        return rel.as_posix()
    except OSError:
        logger.warning("trace payload not saved: %s", request_id, exc_info=True)
        return None


def load_payload(ref: str, *, root: Path | None = None) -> dict[str, Any] | None:
    base = (root or TRACE_ROOT).resolve()
    path = (base / ref).resolve()
    if base not in path.parents:  # 防目录穿越
        return None
    try:
        with gzip.open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
