"""Structured animation scenes rendered by Pillow and FFmpeg."""

from __future__ import annotations

import argparse
import asyncio
import bisect
import json
import math
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field


class AnimationScene(BaseModel):
    kind: Literal["counter", "bars", "line", "flow", "comparison", "keypoints"]
    title: str = Field(max_length=60)
    subtitle: str = Field(default="", max_length=120)
    figure: str = Field(default="", max_length=32)
    unit: str = Field(default="", max_length=20)
    labels: list[str] = Field(default_factory=list, max_length=10)
    values: list[float] = Field(default_factory=list, max_length=10)


async def plan_scenes(brief, draft, style: dict) -> dict:
    from app.services.llm.provider import call_llm_json_with_metadata

    result, _ = await asyncio.wait_for(call_llm_json_with_metadata(
        [
            {"role": "system", "content": (
                "你是动画信息设计师。把给定分镜逐一转换为可渲染 JSON 场景。返回 {scenes:[...]}，数量与分镜一致。"
                "每项包含 kind、title、subtitle、figure、unit、labels、values。"
                "kind 选择 counter（关键数字计数器）、bars（柱状图）、line（曲线）、flow（流程节点）、"
                "comparison（两个对象对照）、keypoints（关键词展开）。"
                "title 为30字以内短标题，subtitle 为50字以内结论，figure 是关键数字或短词，unit 是单位。"
                "labels 是最多10个简短标注，values 是对应的数值。数值取自给定稿件，关系示意在 subtitle 标明示意。"
                "流程用 labels 表示节点；comparison 用两个 labels 表示对象。"
                "按每个分镜的具体意图选择图形，形成计数、增长、流程、对照等多种视觉节奏。"
            )},
            {"role": "user", "content": json.dumps({
                "theme": brief.theme, "intent": brief.intent, "presentation": brief.presentation,
                "shots": [shot.model_dump() for shot in draft.shots],
            }, ensure_ascii=False)},
        ],
        max_tokens=5000, temperature=0.3, scene="studio_animation_plan", routing_group="default",
    ), timeout=120)
    scenes = result.get("scenes", []) if isinstance(result, dict) else []
    if len(scenes) != len(draft.shots):
        raise ValueError("动画场景数量与分镜数量不一致")
    return {
        "title": draft.title,
        "palette": {key: style[key] for key in ("background", "foreground", "accent", "secondary")},
        "scenes": [AnimationScene.model_validate(scene).model_dump() for scene in scenes],
    }


@lru_cache(maxsize=32)
def _font(path: str, size: int):
    return ImageFont.truetype(path, size)


def _lines(draw, text: str, font, width: int) -> list[str]:
    lines, current = [], ""
    for char in text:
        if char == "\n" or (current and draw.textlength(current + char, font=font) > width):
            lines.append(current)
            current = "" if char == "\n" else char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def _text(draw, xy, text, font_path, size, color, width, centered=False, max_lines=3):
    font = _font(font_path, size)
    for index, line in enumerate(_lines(draw, str(text), font, width)[:max_lines]):
        x = xy[0] - draw.textlength(line, font=font) / 2 if centered else xy[0]
        draw.text((x, xy[1] + index * (size + 8)), line, font=font, fill=color)


def _number(value: float) -> str:
    return f"{value:,.0f}" if value.is_integer() else f"{value:,.1f}"


def scene_frame(plan: dict, index: int, local_time: float, width: int, height: int, font_path: str) -> Image.Image:
    scene = plan["scenes"][index]
    palette = plan["palette"]
    bg, fg, accent, secondary = (palette[key] for key in ("background", "foreground", "accent", "secondary"))
    canvas = Image.new("RGB", (960, 540), bg)
    draw = ImageDraw.Draw(canvas)
    duration = scene["duration"]
    progress = min(1.0, max(0.0, local_time / duration))
    enter = 1 - (1 - min(1.0, local_time / 1.8)) ** 3
    labels, values = scene["labels"], scene["values"]
    _text(draw, (48, 25), f"{index + 1:02d} / {len(plan['scenes']):02d}", font_path, 16, accent, 180)
    _text(draw, (48, 60), scene["title"], font_path, 30, fg, 860, max_lines=1)
    draw.line([(48, 112), (912, 112)], fill=secondary, width=2)
    kind = scene["kind"]
    if kind == "counter":
        figure = scene["figure"]
        if values:
            figure = _number(float(values[0]) * enter)
        size = 108
        while draw.textlength(figure, font=_font(font_path, size)) > 790 and size > 30:
            size -= 4
        _text(draw, (480, 145), figure, font_path, size, accent, 800, centered=True, max_lines=1)
        _text(draw, (480, 300), scene["unit"], font_path, 24, fg, 780, centered=True)
        if labels:
            _text(draw, (480, 356), "  ·  ".join(labels), font_path, 21, fg, 800, centered=True, max_lines=1)
    elif kind in {"bars", "line"}:
        values = values or [1.0] * max(1, len(labels))
        labels = labels or [str(i + 1) for i in range(len(values))]
        count = min(len(values), len(labels))
        values, labels = values[:count], labels[:count]
        peak = max(max(values), 1)
        left, right, top, bottom = 88, 878, 166, 358
        for y in (top, (top + bottom) / 2, bottom):
            draw.line([(left, y), (right, y)], fill=secondary, width=1)
        points = []
        for i, value in enumerate(values):
            x = left + (i + 0.5) * (right - left) / count
            step = min(1, max(0, local_time * 0.7 - i * 0.12))
            rise = 1 - (1 - step) ** 3
            y = bottom - max(4, value / peak * (bottom - top)) * rise
            points.append((x, y))
            if kind == "bars":
                half = min(34, (right - left) / count * 0.32)
                draw.rounded_rectangle((x - half, y, x + half, bottom), radius=4, fill=accent if i == count - 1 else secondary)
            elif i > 0:
                draw.line([points[i - 1], points[i]], fill=accent, width=5)
            if kind == "line":
                draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=accent)
            _text(draw, (x, y - 34), _number(float(value)), font_path, 19, fg, 180, centered=True, max_lines=1)
            _text(draw, (x, bottom + 14), labels[i], font_path, 17, fg, 100, centered=True, max_lines=2)
    elif kind == "flow":
        labels = labels or [scene["figure"]]
        count = len(labels)
        columns = min(5, count)
        rows = math.ceil(count / columns)
        active = min(count - 1, int(progress * count * 2) % count)
        for i, label in enumerate(labels):
            x = 480 - (columns - 1) * 82 + (i % columns) * 164
            y = 206 + (i // columns) * (135 if rows > 1 else 30)
            radius = 52 + (4 * math.sin(local_time * 4) if i == active else 0)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=accent if i == active else secondary)
            _text(draw, (x, y - 14), str(i + 1), font_path, 22, bg if i == active else fg, 100, centered=True)
            _text(draw, (x, y + 61), label, font_path, 20, fg, 130, centered=True, max_lines=2)
            if i % columns < columns - 1 and i < count - 1:
                draw.line([(x + 58, y), (x + 102, y)], fill=accent, width=3)
                draw.polygon([(x + 106, y), (x + 94, y - 7), (x + 94, y + 7)], fill=accent)
    elif kind == "comparison":
        for i in range(2):
            x = 92 + i * 434
            draw.rounded_rectangle((x, 151, x + 344, 355), radius=6, outline=secondary, width=3)
            _text(draw, (x + 172, 173), labels[i] if len(labels) > i else "", font_path, 24, fg, 306, centered=True)
            value = _number(float(values[i]) * enter) if len(values) > i else (scene["figure"] if i else scene["unit"])
            _text(draw, (x + 172, 237), value, font_path, 44, accent, 306, centered=True, max_lines=2)
        _text(draw, (480, 226), "↔", font_path, 30, accent, 60, centered=True)
    else:
        labels = labels or [scene["figure"]]
        for i, label in enumerate(labels[:4]):
            y = 152 + i * 55 + int(14 * max(0, 1 - local_time + i * 0.15))
            draw.rectangle((82, y + 8, 90, y + 30), fill=accent)
            _text(draw, (116, y), label, font_path, 27, fg, 752, max_lines=1)
    _text(draw, (480, 412), scene["subtitle"], font_path, 22, fg, 850, centered=True, max_lines=1)
    caption = scene.get("narration", "")
    chunks = _lines(draw, caption, _font(font_path, 19), 816)
    chunk_index = min(len(chunks) - 1, int(progress * len(chunks))) if chunks else 0
    if chunks:
        _text(draw, (480, 464), chunks[chunk_index], font_path, 19, fg, 850, centered=True, max_lines=1)
    draw.rectangle((48, 514, 912, 517), fill=secondary)
    draw.rectangle((48, 514, 48 + 864 * progress, 517), fill=accent)
    fade = min(1.0, local_time / 0.25, (duration - local_time) / 0.3)
    if fade < 1:
        canvas = Image.blend(Image.new("RGB", canvas.size, bg), canvas, max(0, fade))
    if (width, height) != canvas.size:
        result = Image.new("RGB", (width, height), bg)
        canvas.thumbnail((width, height), Image.Resampling.LANCZOS)
        result.paste(canvas, ((width - canvas.width) // 2, (height - canvas.height) // 2))
        return result
    return canvas


def encode_video(plan: dict, directory: Path, on_progress=None) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("需要本地 FFmpeg")
    width, height = plan["width"], plan["height"]
    fps = 24
    bounds = []
    duration = 0.0
    for scene in plan["scenes"]:
        duration += scene["duration"]
        bounds.append(duration)
    audio = directory / "narration.wav"
    output = directory / "preview.mp4"
    args = [
        ffmpeg, "-v", "error", "-nostdin", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0",
        "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-t", str(duration), "-movflags", "+faststart", str(output),
    ]
    font = str(directory / "fonts" / "NotoSansSC.ttf")
    with (directory / "ffmpeg.stderr.log").open("wb") as log:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            frame_count = math.ceil(duration * fps)
            for frame in range(frame_count):
                time = frame / fps
                index = min(len(bounds) - 1, bisect.bisect_right(bounds, time))
                start = bounds[index - 1] if index else 0
                process.stdin.write(scene_frame(plan, index, time - start, width, height, font).tobytes())
                if on_progress and frame % fps == 0:
                    on_progress(min(98, int(frame / frame_count * 98)))
            process.stdin.close()
            if process.wait(timeout=60) != 0:
                raise RuntimeError("动画编码失败，详情见 ffmpeg.stderr.log")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    return output


async def render_storyboard(brief, draft, directory, style, on_progress=None, on_stage=None):
    from app.services.studio_media import MEDIA_ROOT, _synthesize_narration, run_process, tool

    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if on_stage:
        await on_stage("AI 编排动画场景")
    planning = asyncio.create_task(plan_scenes(brief, draft, style))
    try:
        while not planning.done():
            await asyncio.wait([planning], timeout=10)
            if not planning.done() and on_stage:
                await on_stage("AI 编排动画场景")
        plan = await planning
    finally:
        if not planning.done():
            planning.cancel()
            await asyncio.gather(planning, return_exceptions=True)
    plan["width"], plan["height"] = {"16:9": (960, 540), "9:16": (540, 960), "1:1": (720, 720)}[brief.aspect_ratio]
    font = Path(os.environ.get("TOPICEYE_CJK_FONT", "C:/Windows/Fonts/NotoSansSC-VF.ttf"))
    (directory / "fonts").mkdir(exist_ok=True)
    shutil.copyfile(font, directory / "fonts" / "NotoSansSC.ttf")
    if on_stage:
        await on_stage("合成中文旁白")
    for index, (scene, shot) in enumerate(zip(plan["scenes"], draft.shots, strict=True)):
        scene_dir = directory / f"scene-{index + 1:02d}"
        scene_dir.mkdir(exist_ok=True)
        narration = shot.audio.strip()
        if not narration:
            raise ValueError(f"分镜 {index + 1} 需要旁白内容")
        voice = await _synthesize_narration(narration, scene_dir)
        if voice is None:
            raise RuntimeError("中文旁白合成失败，请检查本地中文语音")
        info = json.loads(await run_process([
            tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(voice),
        ]))
        voice_duration = float(info["format"]["duration"])
        duration = max(shot.seconds, voice_duration / 1.45 + 0.2)
        speed = max(0.5, min(2, voice_duration / max(0.1, duration - 0.15)))
        scene["duration"] = round(duration, 3)
        scene["narration"] = narration
        scene["source_shot"] = shot.model_dump()
        await run_process([
            tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-i", str(voice),
            "-af", f"atempo={speed:.5f},apad", "-t", str(duration),
            "-ar", "24000", "-ac", "1", str(scene_dir / "timed.wav"),
        ])
        if on_stage:
            await on_stage(f"合成中文旁白 {index + 1}/{len(draft.shots)}")
    concat = directory / "audio-list.txt"
    concat.write_text("\n".join(f"file 'scene-{i + 1:02d}/timed.wav'" for i in range(len(draft.shots))), encoding="utf-8")
    await run_process([
        tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat), "-c", "copy", str(directory / "narration.wav"),
    ])
    timeline = directory / "timeline.json"
    timeline.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(__file__, directory / "renderer.py")
    (directory / "render.ps1").write_text(
        'Set-Location -LiteralPath $PSScriptRoot\npython renderer.py --plan timeline.json --output .\n', encoding="utf-8",
    )
    (directory / "requirements.txt").write_text("pillow>=11,<13\npydantic>=2,<3\n", encoding="utf-8")
    (directory / "README.md").write_text(
        "# 动画讲解工程\n\npreview.mp4：成片。timeline.json：可编辑动画场景。"
        "\nrenderer.py：Pillow 图形动画源代码。narration.wav：逐段对齐的中文旁白。"
        "\n运行 render.ps1 可以重新渲染，运行环境为 Python、Pillow、Pydantic 和 FFmpeg。\n", encoding="utf-8",
    )
    if on_stage:
        await on_stage("渲染动画画面")
    loop = asyncio.get_running_loop()

    def progress(percent):
        if on_progress:
            asyncio.run_coroutine_threadsafe(on_progress(percent), loop).result()

    output = await asyncio.to_thread(encode_video, plan, directory, progress)
    if not output.is_relative_to(MEDIA_ROOT) or not output.is_file():
        raise RuntimeError("动画输出文件路径无效")
    await run_process([
        tool("ffprobe"), "-v", "error", "-show_entries", "format=duration:stream=codec_type", str(output),
    ])
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", default=".")
    options = parser.parse_args()
    encode_video(json.loads(Path(options.plan).read_text(encoding="utf-8")), Path(options.output).resolve())
