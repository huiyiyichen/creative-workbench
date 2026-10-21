"""把 BibTeX 风格的重音转义还原成 Unicode（arXiv RSS 的作者名：`\\"Ozayta\\c{c}` → `Özaytaç`）。

只处理常见重音命令，不引第三方库；没有反斜杠的字符串原样返回。
"""

from __future__ import annotations

import re
import unicodedata

# 命令 → 组合附加符号
_COMBINING = {
    '"': "\u0308",  # 分音符 ¨
    "'": "\u0301",  # 锐音 ´
    "`": "\u0300",  # 钝音 `
    "^": "\u0302",  # 抑扬 ^
    "~": "\u0303",  # 波浪 ~
    "=": "\u0304",  # 长音 ¯
    ".": "\u0307",  # 上点 ˙
    "c": "\u0327",  # 下加符 ¸
    "u": "\u0306",  # 短音 ˘
    "v": "\u030c",  # 抑扬倒 ˇ
    "H": "\u030b",  # 双锐音 ˝
    "k": "\u0328",  # 反尾形符 ˛
    "r": "\u030a",  # 上圆圈 ˚
}
_LETTERS = {
    "ss": "ß",
    "o": "ø",
    "O": "Ø",
    "l": "ł",
    "L": "Ł",
    "ae": "æ",
    "AE": "Æ",
    "oe": "œ",
    "OE": "Œ",
    "aa": "å",
    "AA": "Å",
    "i": "ı",
}

# \"{O} \"O \c{c} \c c \v{s}
_ACCENT = re.compile(
    r"""\\(["'`^~=.])\s*(?:\{\s*(\\?[A-Za-z])\s*\}|(\\?[A-Za-z]))|\\([cuvHkr])(?:\s*\{\s*(\\?[A-Za-z])\s*\}|\s+([A-Za-z]))"""
)
_LETTER = re.compile(r"\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L|i)(?![A-Za-z])(?:\{\})?")


def _base(ch: str) -> str:
    if ch.startswith("\\"):
        return "ı" if ch[1:] == "i" else ("ȷ" if ch[1:] == "j" else ch[1:])
    return ch


def delatex(text: str | None) -> str | None:
    if not text or "\\" not in text:
        return text

    def accent(m: re.Match[str]) -> str:
        cmd = m.group(1) or m.group(4)
        ch = _base(m.group(2) or m.group(3) or m.group(5) or m.group(6))
        if ch == "ı" and cmd in "\"'`^~=":
            ch = "i"
        return unicodedata.normalize("NFC", ch + _COMBINING[cmd])

    out = _ACCENT.sub(accent, text)
    out = _LETTER.sub(lambda m: _LETTERS[m.group(1)], out)
    # 残留的花括号分组 {Ö} → Ö
    out = re.sub(r"\{([^{}\\]{1,3})\}", r"\1", out)
    return out
