"""空档补采窗口（改造方案 3.7）：同步时由调度方设置，平台信源据此往回翻页。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime

MAX_BACKFILL_DAYS = 7
MAX_BACKFILL_ITEMS = 200


@dataclass(frozen=True)
class BackfillWindow:
    since: datetime
    max_items: int = MAX_BACKFILL_ITEMS


_window: ContextVar[BackfillWindow | None] = ContextVar("backfill_window", default=None)


def current_backfill() -> BackfillWindow | None:
    return _window.get()


@contextmanager
def backfill_window(window: BackfillWindow) -> Iterator[None]:
    token = _window.set(window)
    try:
        yield
    finally:
        _window.reset(token)
