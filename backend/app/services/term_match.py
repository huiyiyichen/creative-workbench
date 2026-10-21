"""追踪词 / 专题关键词的标题匹配。

英文词按整词匹配（PostgreSQL 正则 ``\\m…\\M``，大小写不敏感），避免「rea」命中 real / create 这类子串；
含中文等非 ASCII 字符的词仍按子串匹配（中文没有词边界）。其他数据库（测试用的 SQLite）退回子串匹配。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Boolean, ColumnElement, literal
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnClause

_ASCII_WORD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .+#_-]*$")


def is_ascii_term(term: str) -> bool:
    return bool(_ASCII_WORD.match(term.strip()))


class _WordMatch(ColumnElement[bool]):
    inherit_cache = True
    type = Boolean()

    def __init__(self, column: Any, term: str) -> None:
        self.column = column
        self.term = term


@compiles(_WordMatch, "postgresql")
def _pg_word_match(element: _WordMatch, compiler: Any, **kw: Any) -> str:
    pattern = r"\m" + re.escape(element.term).replace(r"\ ", " ") + r"\M"
    return compiler.process(element.column.op("~*")(literal(pattern)), **kw)


@compiles(_WordMatch)
def _default_word_match(element: _WordMatch, compiler: Any, **kw: Any) -> str:
    return compiler.process(element.column.ilike(f"%{element.term}%"), **kw)


def title_matches(column: ColumnClause | ColumnElement, term: str) -> ColumnElement[bool]:
    term = term.strip()
    if is_ascii_term(term):
        return _WordMatch(column, term)
    return column.ilike(f"%{term}%")
