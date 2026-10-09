"""Native media operations use fixed FFmpeg graphs, never model-authored code."""

import asyncio
import json
import math
import os
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core.exceptions import AppException, ValidationError
from app.schemas.studio import StudioBrief, StudioDraft
from app.services.studio_catalog import resolve

MEDIA_ROOT = (Path(__file__).resolve().parents[2] / "data" / "studio").resolve()
MAX_AUDIO_BYTES = 50 * 1024 * 1024
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

NEUTRAL_STYLE = {
    "id": "neutral",
    "name": "中性排版",
    "background": "#111111",
    "foreground": "#F5F5F5",
    "accent": "#4FC3F7",
    "secondary": "#263238",
}


def _render_style(brief: StudioBrief, style_override: dict | None = None) -> dict:
    if style_override is not None:
        return style_override
    _, style = resolve(brief)
    return style or NEUTRAL_STYLE


def safe_path(relative: str) -> Path:
    path = (MEDIA_ROOT / relative).resolve()
    if path == MEDIA_ROOT or not path.is_relative_to(MEDIA_ROOT):
        raise ValidationError("素材路径无效")
    return path


def tool(name: str) -> str:
    candidate = shutil.which(name)
    if not candidate:
        raise AppException(f"未找到 {name}，本地制作不可用", 503)
    return candidate


async def run_process(args: list[str], *, cwd: Path | None = None, timeout: float = 60) -> bytes:
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError from None
    if completed.returncode != 0:
        # FFmpeg diagnostics may contain private paths and metadata; do not expose them.
        raise ValidationError("媒体处理失败，请检查音频编码、字体和文件完整性")
    return completed.stdout


async def probe_audio(path: Path) -> float:
    raw = await run_process([
        tool("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_entries", "format=duration,format_name:stream=codec_type", "-of", "json", str(path),
    ], timeout=20)
    result = json.loads(raw)
    formats = set(result.get("format", {}).get("format_name", "").split(","))
    if not formats.intersection({"mp3", "wav", "mov", "mp4", "m4a", "ogg", "flac"}):
        raise ValidationError("只支持 MP3、WAV、M4A、OGG 和 FLAC 音频")
    if not any(stream.get("codec_type") == "audio" for stream in result.get("streams", [])):
        raise ValidationError("文件不包含音轨")
    duration = float(result.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or not 5 <= duration <= 600:
        raise ValidationError("音频时长需在 5 秒至 10 分钟之间")
    return duration


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{fraction:02d}"


def ass_text(text: str) -> str:
    return text.replace("\\", "/").replace("{", "｛").replace("}", "｝").replace("\r", "").replace("\n", r"\N")


def ass_color(color: str) -> str:
    hex_value = color.lstrip("#")
    return "&H00" + hex_value[4:6] + hex_value[2:4] + hex_value[0:2]


def subtitle_track(brief: StudioBrief, draft: StudioDraft, width: int, height: int, style_override: dict | None = None) -> str:
    style = _render_style(brief, style_override)
    font_size = 32 if width >= 900 else 26
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Noto Sans SC,{font_size},{ass_color(style['foreground'])},&H00000000,{ass_color(style['background'])},&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,40,40,{int(height * 0.21)},1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = []
    for index, cue in enumerate(draft.cues):
        end = draft.cues[index + 1].time if index + 1 < len(draft.cues) else brief.duration_seconds
        end = min(end, cue.time + 12, brief.duration_seconds)
        if end > cue.time:
            events.append(f"Dialogue: 0,{ass_time(cue.time)},{ass_time(end)},Default,,0,0,0,,{ass_text(cue.text)}")
    return header + "\n".join(events) + "\n"


def native_filter(brief: StudioBrief, width: int, height: int, style_override: dict | None = None) -> str:
    style = _render_style(brief, style_override)
    wave_height = max(32, int(height * 0.12))
    if style["id"] == "swiss":
        x, y = "W*0.1", "H*0.23"
        circle = "[3:v]null[shape];"
    elif style["id"] == "constructivism":
        x, y = "W*0.1+W*0.35*t/" + str(brief.duration_seconds), "H*0.13"
        circle = "[3:v]rotate=0.5:fillcolor=none[shape];"
    elif style["id"] == "brutalism":
        x, y = "W*0.12+W*0.45*abs(sin(t*0.2))", "H*0.15"
        circle = "[3:v]null[shape];"
    else:
        x, y = "W*0.22+W*0.12*sin(t*0.6)", "H*0.19+H*0.08*cos(t*0.5)"
        circle = (
            "[3:v]format=rgba,geq="
            "r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            "a='if(lte((X-W/2)^2+(Y-H/2)^2,(W/2)^2),255,0)'[shape];"
        )
    # All expressions and filenames are program-owned, not interpolated user text.
    return (
        f"[0:a]asplit=2[aout][wave];[wave]showwaves=s={width - 80}x{wave_height}:"
        f"mode=cline:rate=25:colors={style['accent']}[wv];"
        f"{circle}[1:v][2:v]overlay=x='{x}':y='{y}':shortest=1[base];"
        f"[base][shape]overlay=x='W*0.69+W*0.05*cos(t*0.4)':y='H*0.25':shortest=1[geo];"
        f"[geo][wv]overlay=40:{height - wave_height - 20}:shortest=1,"
        f"drawbox=x=40:y=40:w={width - 80}:h=3:color={style['foreground']}:t=fill,"
        "subtitles=lyrics.ass:fontsdir=fonts[v]"
    )


async def render_native_mv(
    brief: StudioBrief, draft: StudioDraft, audio: Path, directory: Path,
    style_override: dict | None = None,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
) -> Path:
    style = _render_style(brief, style_override)
    width, height = {"16:9": (960, 540), "9:16": (540, 960), "1:1": (720, 720)}[brief.aspect_ratio]
    directory.mkdir(parents=True, exist_ok=True)
    fonts = directory / "fonts"
    fonts.mkdir(exist_ok=True)
    # The replaceable font slot requires an installed open-source Chinese font.
    font = Path(os.environ.get("TOPICEYE_CJK_FONT", "C:/Windows/Fonts/NotoSansSC-VF.ttf"))
    if not font.is_file():
        raise AppException("未找到 Noto Sans SC 字体，请配置 TOPICEYE_CJK_FONT", 503)
    await asyncio.to_thread(shutil.copyfile, font, fonts / "NotoSansSC.ttf")
    await asyncio.to_thread(
        (directory / "lyrics.ass").write_text,
        subtitle_track(brief, draft, width, height, style), encoding="utf-8",
    )
    square = max(50, int(width * 0.12))
    second = max(40, int(width * 0.16))
    shape = max(50, int(width * 0.18))
    duration = str(brief.duration_seconds)
    output = directory / "video.mp4"
    args = [
        tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-progress", "pipe:1", "-nostats",
        "-protocol_whitelist", "file,pipe", "-i", str(audio),
        "-f", "lavfi", "-i", f"color=c={style['background']}:s={width}x{height}:r=25:d={duration}",
        "-f", "lavfi", "-i", f"color=c={style['accent']}:s={square}x{square}:r=25:d={duration}",
        "-f", "lavfi", "-i", f"color=c={style['secondary']}:s={second}x{second}:r=25:d={duration}",
        "-f", "lavfi", "-i", f"color=c={style['foreground']}:s={shape}x{shape}:r=25:d={duration}",
        "-filter_complex", native_filter(brief, width, height, style), "-map", "[v]", "-map", "[aout]",
        "-t", duration, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output),
    ]
    process = await asyncio.create_subprocess_exec(
        *args, cwd=directory, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stderr_task = asyncio.create_task(process.stderr.read())
    try:
        async with asyncio.timeout(max(120, brief.duration_seconds * 8)):
            while line := await process.stdout.readline():
                key, _, value = line.decode("utf-8", errors="replace").strip().partition("=")
                if key == "out_time_us" and value.isdigit() and on_progress:
                    await on_progress(min(98, int(int(value) / 1_000_000 / brief.duration_seconds * 98)))
            code = await process.wait()
            await stderr_task
            if code != 0:
                raise ValidationError("视频合成失败，请检查音频与字体")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        if not stderr_task.done():
            stderr_task.cancel()
        await asyncio.gather(stderr_task, return_exceptions=True)
    await run_process([tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", str(output)])
    return output


async def _synthesize_narration(text: str, directory: Path) -> Path | None:
    if not text.strip() or not shutil.which("powershell.exe"):
        return None
    script = directory / "synthesize_narration.ps1"
    source = directory / "narration.txt"
    output = directory / "narration.wav"
    source.write_text(text.strip(), encoding="utf-8")
    script.write_text(
        "param([string]$InputFile, [string]$OutputFile)\n"
        "Add-Type -AssemblyName System.Speech\n"
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "try {\n"
        "  $synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female, "
        "[System.Speech.Synthesis.VoiceAge]::Adult, 0, "
        "[Globalization.CultureInfo]::GetCultureInfo('zh-CN'))\n"
        "  $synth.SetOutputToWaveFile($OutputFile)\n"
        "  $synth.Speak((Get-Content -LiteralPath $InputFile -Raw -Encoding UTF8))\n"
        "} finally { $synth.Dispose() }\n",
        encoding="utf-8",
    )
    completed = await asyncio.to_thread(
        subprocess.run,
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(script), str(source), str(output),
        ],
        cwd=directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    return output if completed.returncode == 0 and output.is_file() else None


async def render_animation_video(
    brief: StudioBrief,
    draft: StudioDraft,
    directory: Path,
    style_override: dict | None = None,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
    on_stage: Callable[[str], Awaitable[None]] | None = None,
) -> Path:
    from app.services.studio_animation import render_storyboard

    return await render_storyboard(brief, draft, directory, _render_style(brief, style_override), on_progress, on_stage)
