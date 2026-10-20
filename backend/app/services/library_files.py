"""灵感库文件存储（改造方案 6.3）。

* 原文件存 ``data/library/<sha 前两位>/<sha256><后缀>``，按 sha256 去重；库里只记相对路径。
* 图片生成 320px / 960px WebP 缩略图，取主色与 5 色色板；视频片段截封面帧、读时长；音频读时长并生成波形。
* 字体读取字体名和字重，生成字样预览。
* 外部生成图读取 PNG 元数据里的提示词和参数（SD WebUI 的 ``parameters``、ComfyUI 的 ``prompt`` / ``workflow``）。
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

LIBRARY_ROOT = (Path(__file__).resolve().parents[2] / "data" / "library").resolve()
MAX_BYTES = 500 * 1024 * 1024

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".tif", ".tiff", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2", ".ttc"}
PALETTE_EXT = {".ase", ".aco", ".gpl"}

THUMB_SIZES = {"small": 320, "large": 960}


class LibraryFileError(ValueError):
    pass


@dataclass
class StoredFile:
    sha256: str
    path: str  # 相对 LIBRARY_ROOT
    name: str
    mime: str
    bytes: int
    asset_kind: str
    thumb_small: str | None = None
    thumb_large: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    dominant_color: str | None = None
    palette: list[str] | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    generated: bool = False  # PNG 元数据里有生成参数


def classify(name: str, mime: str | None = None) -> str:
    ext = Path(name).suffix.lower()
    if ext in FONT_EXT:
        return "font"
    if ext in AUDIO_EXT or (mime or "").startswith("audio/"):
        return "audio"
    if ext in VIDEO_EXT or ext == ".gif" or (mime or "").startswith("video/"):
        return "motion"
    if ext in PALETTE_EXT:
        return "palette"
    if ext in IMAGE_EXT or (mime or "").startswith("image/"):
        return "image"
    return "file"


def abs_path(relative: str) -> Path:
    p = (LIBRARY_ROOT / relative).resolve()
    if p == LIBRARY_ROOT or not p.is_relative_to(LIBRARY_ROOT):
        raise LibraryFileError("路径无效")
    return p


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb[:3])


def palette_of(img: Image.Image, colors: int = 5) -> list[str]:
    small = img.convert("RGB").copy()
    small.thumbnail((128, 128))
    q = small.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    out = []
    for _, idx in counts[:colors]:
        out.append(_hex(tuple(pal[idx * 3 : idx * 3 + 3])))  # type: ignore[arg-type]
    return out


def parse_generation_meta(img: Image.Image) -> dict[str, Any]:
    """SD WebUI ``parameters``：正向提示词、``Negative prompt:``、最后一行参数；ComfyUI ``prompt`` / ``workflow`` JSON。"""
    info = getattr(img, "info", {}) or {}
    out: dict[str, Any] = {}
    params = info.get("parameters")
    if isinstance(params, str) and params.strip():
        lines = params.strip().split("\n")
        settings_line = lines[-1] if re.search(r"Steps:\s*\d+", lines[-1]) else ""
        body = lines[:-1] if settings_line else lines
        text = "\n".join(body)
        prompt, _, negative = text.partition("Negative prompt:")
        out["tool"] = "sd-webui"
        out["prompt"] = prompt.strip()
        if negative.strip():
            out["negative_prompt"] = negative.strip()
        settings: dict[str, str] = {}
        for part in re.split(r",\s*(?=[A-Za-z][\w ]*:)", settings_line):
            if ":" in part:
                k, _, v = part.partition(":")
                settings[k.strip()] = v.strip()
        if settings:
            out["params"] = settings
            if "Model" in settings:
                out["model"] = settings["Model"]
    for key in ("prompt", "workflow"):
        raw = info.get(key)
        if isinstance(raw, str) and raw.strip().startswith("{"):
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            out["tool"] = "comfyui"
            out[f"comfy_{key}"] = data
            if key == "prompt" and "prompt" not in out:
                texts = [
                    n.get("inputs", {}).get("text")
                    for n in data.values()
                    if isinstance(n, dict) and isinstance(n.get("inputs", {}).get("text"), str)
                ]
                if texts:
                    out["prompt"] = texts[0]
                    if len(texts) > 1:
                        out["negative_prompt"] = texts[1]
                ckpt = [
                    n.get("inputs", {}).get("ckpt_name")
                    for n in data.values()
                    if isinstance(n, dict) and n.get("inputs", {}).get("ckpt_name")
                ]
                if ckpt:
                    out["model"] = ckpt[0]
    return out


def _save_thumbs(img: Image.Image, sha: str) -> dict[str, str]:
    out = {}
    base = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
    for name, size in THUMB_SIZES.items():
        t = base.copy()
        t.thumbnail((size, size))
        rel = f"thumbs/{sha[:2]}/{sha}-{size}.webp"
        p = abs_path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        t.save(p, "WEBP", quality=82)
        out[name] = rel
    return out


def _ffprobe_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return round(float(r.stdout.strip()), 2) if r.stdout.strip() else None
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


def _video_frame(path: Path, at: float = 1.0) -> Image.Image | None:
    if not shutil.which("ffmpeg"):
        return None
    try:
        r = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(at),
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if r.stdout:
            return Image.open(io.BytesIO(r.stdout))
    except (subprocess.SubprocessError, OSError):
        return None
    return None


def audio_waveform(path: Path, points: int = 80) -> list[float] | None:
    """用 ffmpeg 解出 8kHz 单声道 PCM，按段取峰值，0–1。"""
    if not shutil.which("ffmpeg"):
        return None
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    data = r.stdout
    if len(data) < 4:
        return None
    import array

    samples = array.array("h")
    samples.frombytes(data[: len(data) // 2 * 2])
    n = len(samples)
    step = max(1, n // points)
    peaks = [max(abs(s) for s in samples[i : i + step]) for i in range(0, n, step)][:points]
    top = max(peaks) or 1
    return [round(p / top, 3) for p in peaks]


def font_info(path: Path) -> dict[str, Any]:
    try:
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover
        return {}
    try:
        font = TTFont(str(path), fontNumber=0, lazy=True)
    except Exception:  # noqa: BLE001 — 坏字体不阻止入库
        logger.debug("忽略的异常（library_files.py）", exc_info=True)
        return {}
    names = {}
    for rec in font["name"].names:
        try:
            names.setdefault(rec.nameID, rec.toUnicode())
        except Exception:  # noqa: BLE001
            logger.debug("忽略的异常（library_files.py）", exc_info=True)
            continue
    weight = None
    if "OS/2" in font:
        weight = getattr(font["OS/2"], "usWeightClass", None)
    return {"family": names.get(16) or names.get(1), "style": names.get(17) or names.get(2), "weight": weight}


def font_specimen(path: Path, sha: str, family: str | None) -> dict[str, str] | None:
    try:
        font = ImageFont.truetype(str(path), 64)
        small = ImageFont.truetype(str(path), 28)
    except OSError:
        return None
    img = Image.new("RGB", (960, 300), (21, 24, 29))
    d = ImageDraw.Draw(img)
    d.text((40, 40), "创意工作台 Aa 123", font=font, fill=(232, 234, 237))
    d.text((40, 170), (family or "") + "  永和九年，岁在癸丑", font=small, fill=(141, 150, 163))
    return _save_thumbs(img, sha)


def store_bytes(content: bytes, filename: str, mime: str | None = None) -> StoredFile:
    if not content:
        raise LibraryFileError("文件为空")
    if len(content) > MAX_BYTES:
        raise LibraryFileError("文件超过 500 MB")
    sha = hashlib.sha256(content).hexdigest()
    ext = Path(filename or "").suffix.lower()[:10] or (mimetypes.guess_extension(mime or "") or "")
    rel = f"{sha[:2]}/{sha}{ext}"
    path = abs_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    mime = mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    kind = classify(filename, mime)
    sf = StoredFile(
        sha256=sha, path=rel, name=Path(filename or rel).name[:255], mime=mime, bytes=len(content), asset_kind=kind
    )

    if kind == "image" or (kind == "motion" and ext == ".gif"):
        try:
            img = Image.open(io.BytesIO(content))
            img.load()
        except Exception as exc:  # noqa: BLE001
            if ext == ".svg":
                return sf
            raise LibraryFileError("无法读取图片") from exc
        sf.width, sf.height = img.size
        sf.meta = parse_generation_meta(img)
        sf.generated = bool(sf.meta.get("prompt") or sf.meta.get("comfy_prompt"))
        frame = img.convert("RGB")
        sf.palette = palette_of(frame)
        sf.dominant_color = sf.palette[0] if sf.palette else None
        thumbs = _save_thumbs(frame if kind == "image" else img.convert("RGB"), sha)
        sf.thumb_small, sf.thumb_large = thumbs["small"], thumbs["large"]
        if kind == "motion":
            sf.duration = round(getattr(img, "n_frames", 1) * (img.info.get("duration", 100) or 100) / 1000, 2)
    elif kind == "motion":
        sf.duration = _ffprobe_duration(path)
        frame = _video_frame(path, at=min(1.0, (sf.duration or 2) / 2))
        if frame is not None:
            sf.width, sf.height = frame.size
            sf.palette = palette_of(frame)
            sf.dominant_color = sf.palette[0] if sf.palette else None
            thumbs = _save_thumbs(frame.convert("RGB"), sha)
            sf.thumb_small, sf.thumb_large = thumbs["small"], thumbs["large"]
    elif kind == "audio":
        sf.duration = _ffprobe_duration(path)
        wave = audio_waveform(path)
        if wave:
            sf.meta["waveform"] = wave
    elif kind == "font":
        info = font_info(path)
        sf.meta.update({k: v for k, v in info.items() if v is not None})
        thumbs = font_specimen(path, sha, info.get("family"))
        if thumbs:
            sf.thumb_small, sf.thumb_large = thumbs["small"], thumbs["large"]
    return sf


def video_frame_at(relative: str, at: float) -> bytes | None:
    """从内容取图：视频截帧（指定时间点），返回 PNG 字节。"""
    frame = _video_frame(abs_path(relative), at=at)
    if frame is None:
        return None
    buf = io.BytesIO()
    frame.save(buf, "PNG")
    return buf.getvalue()


def disk_usage() -> dict[str, int]:
    total = files = 0
    if LIBRARY_ROOT.exists():
        for p in LIBRARY_ROOT.rglob("*"):
            if p.is_file():
                files += 1
                total += p.stat().st_size
    return {"bytes": total, "files": files}
