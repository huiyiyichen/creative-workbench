"""截断 JSON 的抢救：模型输出被 max_tokens 截断时，保留已经完整的部分。

例如 ``{"cards":[{"title":"a"},{"title":"b","angle":"写到一半`` →
``{"cards":[{"title":"a"}]}``。只在最后一个「完整的值」之后截断再补齐括号，
不猜测被截断的内容。
"""

from __future__ import annotations

import json
from typing import Any


def salvage_truncated_json(text: str) -> Any | None:
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    s = text[start:]
    stack: list[str] = []
    in_str = False
    esc = False
    best: tuple[int, list[str]] | None = None  # (截断位置, 当时的括号栈)
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            if not stack:
                try:
                    return json.loads(s[: i + 1])
                except json.JSONDecodeError:
                    return None
            # 刚闭合的是数组里的一个元素 / 对象里的一个值：这里截断是安全的
            best = (i + 1, list(stack))
    if best is None:
        return None
    cut, open_stack = best
    closers = "".join("}" if c == "{" else "]" for c in reversed(open_stack))
    try:
        out = json.loads(s[:cut] + closers)
    except json.JSONDecodeError:
        return None
    return out if out else None
