"""模型调用的溯源上下文（改造方案 2.3）。

调用方用 ``with llm_call_context(content_id=..., run_id=...)`` 包住一次分析 / 生成，
其中的每次模型调用写入 ``llm_call_logs`` 时会带上这些 id。基于 ContextVar，
并发任务互不干扰。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LlmCallContext:
    content_id: int | None = None
    run_id: str | None = None
    step_id: str | None = None
    project_id: int | None = None


_current: ContextVar[LlmCallContext] = ContextVar("llm_call_context", default=LlmCallContext())


def current_llm_context() -> LlmCallContext:
    return _current.get()


@contextmanager
def llm_call_context(**fields) -> Iterator[LlmCallContext]:
    """在当前上下文上叠加字段（未给出的字段沿用外层）。"""
    ctx = replace(_current.get(), **{k: v for k, v in fields.items() if v is not None})
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)
