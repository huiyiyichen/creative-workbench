from __future__ import annotations

import json
import re
import shutil
import textwrap
import wave
from pathlib import Path

from app.core.exceptions import ValidationError
from app.services.studio_media import ass_text, ass_time, run_process, tool


def caption_track(timeline: dict, workspace: Path) -> list[dict]:
    captions = []
    cursor = 0.0
    width = max(10, min(24, (timeline["width"] - 160) // 48))
    for scene in timeline["scenes"]:
        voice_file = scene.get("voiceFile")
        if voice_file and scene.get("audio"):
            with wave.open(str(workspace / "public" / voice_file)) as audio:
                duration = audio.getnframes() / audio.getframerate()
            phrases = re.split(r"(?<=[，。！？；：])", scene["audio"])
            chunks = [
                chunk
                for phrase in phrases
                for chunk in textwrap.wrap(
                    phrase,
                    width=width,
                    break_on_hyphens=False,
                )
                if chunk.strip()
            ]
            weights = [len(chunk.strip()) for chunk in chunks]
            total = sum(weights)
            position = cursor
            for chunk, weight in zip(chunks, weights, strict=True):
                end = position + duration * weight / total
                captions.append({"start": round(position, 3), "end": round(end, 3), "text": chunk})
                position = end
        cursor += scene["frames"] / timeline["fps"]
    return captions


def _srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, fraction = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{fraction:03}"


def write_subtitles(workspace: Path, timeline: dict, *, required: bool = False) -> None:
    captions = caption_track(timeline, workspace)
    if required:
        narration = "".join(scene.get("audio", "") for scene in timeline["scenes"])
        text = "".join(cue["text"] for cue in captions)
        if not captions or re.sub(r"\s+", "", text) != re.sub(r"\s+", "", narration):
            raise ValidationError("动画讲解需要覆盖完整旁白的中文字幕")
    timeline["captions"] = captions
    (workspace / "narration.srt").write_text(
        "\n\n".join(
            f"{index}\n{_srt_time(cue['start'])} --> {_srt_time(cue['end'])}\n{cue['text']}"
            for index, cue in enumerate(captions, 1)
        )
        + "\n",
        encoding="utf-8",
    )
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {timeline['width']}
PlayResY: {timeline['height']}
WrapStyle: 0
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Noto Sans SC,48,&H00FFFFFF,&H000000FF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,3,10,0,2,80,80,48,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    (workspace / "narration.ass").write_text(
        header
        + "\n".join(
            f"Dialogue: 0,{ass_time(cue['start'])},{ass_time(cue['end'])},Default,,0,0,0,,{ass_text(cue['text'])}"
            for cue in captions
        )
        + "\n",
        encoding="utf-8",
    )


def install_subtitle_layer(workspace: Path, timeline: dict, *, required: bool = False) -> None:
    write_subtitles(workspace, timeline, required=required)
    (workspace / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    template = Path(__file__).resolve().parents[2] / "media_runtime/template/src/index.tsx"
    shutil.copyfile(template, workspace / "src/index.tsx")


async def subtitle_existing_video(workspace: Path) -> Path:
    timeline = json.loads((workspace / "timeline.json").read_text(encoding="utf-8"))
    write_subtitles(workspace, timeline)
    (workspace / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    output = workspace / "dist/preview.mp4"
    subtitled = workspace / "dist/preview-subtitled.mp4"
    await run_process(
        [
            tool("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(output),
            "-vf",
            "subtitles=narration.ass:fontsdir=public/fonts",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(subtitled),
        ],
        cwd=workspace,
        timeout=180,
    )
    subtitled.replace(output)
    (workspace / "dist/timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    template = Path(__file__).resolve().parents[2] / "media_runtime/template/src/index.tsx"
    shutil.copyfile(template, workspace / "src/index.tsx")
    return output
