import re

from app.core.exceptions import ValidationError
from app.schemas.studio import LyricCue

TIMESTAMP = re.compile(r"\[(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?\]")
OFFSET = re.compile(r"\[offset:([+-]?\d+)\]", re.IGNORECASE)


def parse_lrc(text: str, duration: float | None = None) -> list[LyricCue]:
    if len(text) > 250000:
        raise ValidationError("LRC 文件超过 250 KB")
    offset_match = OFFSET.search(text)
    offset = int(offset_match.group(1)) / 1000 if offset_match else 0
    if abs(offset) > 600:
        raise ValidationError("LRC offset 超出范围")
    grouped: dict[float, list[str]] = {}
    for line in text.lstrip("\ufeff").splitlines():
        stamps = list(TIMESTAMP.finditer(line))
        if not stamps:
            continue
        lyric = TIMESTAMP.sub("", line).strip()
        if not lyric:
            continue
        if len(lyric) > 500:
            raise ValidationError("单行歌词超过 500 字")
        for stamp in stamps:
            fraction = stamp.group(3) or "0"
            seconds = int(stamp.group(1)) * 60 + int(stamp.group(2)) + float(f"0.{fraction}") + offset
            if seconds < 0 or seconds > 600 or (duration is not None and seconds >= duration):
                raise ValidationError("歌词时间戳超出音频范围")
            key = round(seconds, 3)
            grouped.setdefault(key, [])
            if lyric not in grouped[key]:
                grouped[key].append(lyric)
    if not grouped:
        raise ValidationError("未找到有效的 [mm:ss.xx] 歌词时间戳")
    if len(grouped) > 1500:
        raise ValidationError("歌词时间轴超过 1500 条")
    return [LyricCue(time=time, text="\n".join(lines)) for time, lines in sorted(grouped.items())]
