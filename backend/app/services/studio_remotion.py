from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.services.studio_media import run_process, tool
from app.services.studio_subtitles import write_subtitles
from app.services.studio_tts import synthesize_speech, tts_config

RUNTIME = Path(__file__).resolve().parents[2] / "media_runtime"
FRAME_RATE = 30
DESIGN_PROMPT = (
    "你是动画导演和前端工程师。读取当前目录 production_spec.json、timeline.json 与 src/components.tsx，"
    "把冻结分镜设计为内容专属、细节完整的 Remotion 动画。交付 src/Scenes.tsx，"
    "export const Scene: React.FC<SceneProps>，SceneProps 从 ./components 导入。"
    "用 index 区分分镜，useCurrentFrame 获取当前分镜内帧，scene.frames 为实际时长。"
    "画面严格按 timeline 的 width/height 设计，使用 useVideoConfig 获取尺寸。"
    "复用 Stage/Reveal/AnimatedNumber/Connector/Label/Caption，或制作自定义 React、SVG、Canvas、Three.js 画面。"
    "每个分镜有独立视觉意图、清晰的信息层级和连续的元素运动；中文使用 Workbench 字体。"
    "完整旁白的中文字幕由工作台独立生成和渲染。画面底部 140 像素留给字幕，其余信息在上方构图。"
    "画面强调文字与完整旁白字幕是两个独立层。"
    "技术文件 index.tsx、render.mjs、timeline.json 与配音素材保持原样。"
    "工作台负责编译、画面检查与完整视频渲染。当前任务交付动画源码，完成后写入 design.ready.json："
    '{"entry":"src/Scenes.tsx"}，随后返回。所有制作文件保存在当前目录。'
)


def harness_details() -> dict:
    home = Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh")))
    settings_path = home / "settings.yaml"
    settings_text = settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
    provider = next(
        (line.split(":", 1)[1].strip() for line in settings_text.splitlines() if line.strip().startswith("provider:")),
        "deepseek-official",
    )
    model = next(
        (line.split(":", 1)[1].strip() for line in settings_text.splitlines() if line.strip().startswith("model:")),
        "deepseek-flash",
    )
    return {
        "engine": "DeepSeek Harness",
        "provider": provider,
        "model": model,
        "requested_effort": "medium",
        "reasoning_effort": "high",
    }


def harness_command(workspace: Path, prompt: str) -> list[str]:
    cli = shutil.which("dsh")
    if not cli:
        raise ValidationError("请安装本机 DeepSeek Harness（dsh）")
    path = Path(cli)
    entry = path.parent / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    launcher = [tool("node"), str(entry)] if entry.exists() else [cli]
    overlay = workspace / "harness.patch.yml"
    overlay.write_text(
        "- id: headless-runner\n"
        "  config:\n"
        "    task: !!js |\n"
        "      (() => {\n"
        "        const model = ctx.agentDefaultModel;\n"
        "        const selection = model.currentSelection.bind(model);\n"
        "        model.currentSelection = () => ({...selection(), reasoningEffort: 'high'});\n"
        "        return ctx.headlessStartup.task;\n"
        "      })()\n",
        encoding="utf-8",
    )
    return [*launcher, "--profile", "headless", "--patch", str(overlay), prompt]


async def design_animation(workspace: Path, on_stage) -> None:
    command = harness_command(workspace, DESIGN_PROMPT)
    started = time.monotonic()
    ready = workspace / "design.ready.json"
    with (
        (workspace / "harness.stdout.log").open("w", encoding="utf-8", errors="replace") as stdout,
        (workspace / "harness.stderr.log").open("w", encoding="utf-8", errors="replace") as stderr,
    ):
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "DSH_TELEMETRY_DISABLED": "1"},
        )
        try:
            while process.poll() is None and not ready.is_file():
                await asyncio.sleep(2)
                await on_stage("DeepSeek 设计动画")
                if time.monotonic() - started >= 600:
                    raise ValidationError("DeepSeek 动画源码交付超时")
            if not ready.is_file() and process.returncode != 0:
                raise ValidationError("DeepSeek 动画设计失败，请查看 harness.stderr.log")
        finally:
            if process.poll() is None:
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            await asyncio.to_thread(process.wait)


async def prepare_animation(
    db: AsyncSession,
    workspace: Path,
    brief,
    draft,
    style: dict,
    on_stage,
    soundtrack: Path | None = None,
    reuse_design: bool = False,
) -> dict:
    shutil.copytree(
        RUNTIME / "template",
        workspace,
        dirs_exist_ok=True,
        ignore=(lambda _directory, names: ["Scenes.tsx"] if reuse_design and "Scenes.tsx" in names else []),
    )
    shutil.copyfile(RUNTIME / "package.json", workspace / "package.json")
    shutil.copyfile(RUNTIME / "package-lock.json", workspace / "package-lock.json")
    modules = workspace / "node_modules"
    if not modules.exists():
        # A junction reuses the installed rendering toolchain on Windows.
        await run_process(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path '{str(modules).replace(chr(39), chr(39) * 2)}' "
                f"-Target '{str(RUNTIME / 'node_modules').replace(chr(39), chr(39) * 2)}' | Out-Null",
            ]
        )
    fonts = workspace / "public" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        os.environ.get("TOPICEYE_CJK_FONT", "C:/Windows/Fonts/NotoSansSC-VF.ttf"),
        fonts / "NotoSansSC.ttf",
    )
    config = await tts_config(db, with_secret=True) if soundtrack is None else None
    scenes = []
    for index, shot in enumerate(draft.shots):
        scene = shot.model_dump()
        duration = shot.seconds
        if config is not None:
            if not shot.audio.strip():
                raise ValidationError(f"分镜 {index + 1} 需要旁白")
            await on_stage(f"千问配音 {index + 1}/{len(draft.shots)}")
            voice_file = f"voice/scene-{index + 1:02d}.wav"
            voice = await synthesize_speech(shot.audio, config, workspace / "public" / voice_file)
            metadata = json.loads(
                await run_process(
                    [
                        tool("ffprobe"),
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "json",
                        str(voice),
                    ]
                )
            )
            duration = max(duration, float(metadata["format"]["duration"]) + 0.2)
            scene["voiceFile"] = voice_file
        scene["frames"] = max(1, math.ceil(duration * FRAME_RATE))
        scenes.append(scene)
    if not scenes:
        raise ValidationError("请先生成动画分镜")
    width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[brief.aspect_ratio]
    timeline = {
        "width": width,
        "height": height,
        "fps": FRAME_RATE,
        "palette": {key: style[key] for key in ("background", "foreground", "accent", "secondary")},
        "scenes": scenes,
        "soundtrack": "",
    }
    if soundtrack is not None:
        name = f"soundtrack{soundtrack.suffix}"
        shutil.copyfile(soundtrack, workspace / "public" / name)
        timeline["soundtrack"] = name
    write_subtitles(workspace, timeline, required=brief.mode == "animation_video")
    (workspace / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace / "render.ps1").write_text(
        "Set-Location -LiteralPath $PSScriptRoot\n" "if (!(Test-Path node_modules)) { npm ci }\n" "node render.mjs\n",
        encoding="utf-8",
    )
    (workspace / "AGENTS.md").write_text(
        "# Animation project\n\n"
        "Work in this project directory. Read production_spec.json, timeline.json and src/components.tsx.\n"
        "Create the storyboard-specific src/Scenes.tsx. Reuse primitives or create custom React, SVG, Canvas, "
        "Three.js and CSS visuals. Use Remotion frame-based animation. Hand off completed source "
        "by writing design.ready.json and returning. The controller compiles, checks and renders the project.\n"
        "The frozen narration and timeline define the spoken content and scene timing.\n",
        encoding="utf-8",
    )
    return timeline


async def render_animation(workspace: Path, on_progress) -> Path:
    env = os.environ.copy()
    browser = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if browser.exists():
        env["WORKBENCH_BROWSER"] = str(browser)
    stderr = (workspace / "render.stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [tool("node"), str(workspace / "render.mjs")],
        cwd=workspace,
        env=env,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        async with asyncio.timeout(1200):
            while line := await asyncio.to_thread(process.stdout.readline):
                try:
                    status = json.loads(line)
                except ValueError:
                    continue
                await on_progress(status.get("stage", "渲染动画"), status.get("percent"))
            code = await asyncio.to_thread(process.wait)
    finally:
        if process.poll() is None:
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            await asyncio.to_thread(process.wait)
        process.stdout.close()
        stderr.close()
    output = workspace / "dist" / "preview.mp4"
    if code != 0 or not output.exists():
        raise ValidationError("动画工程渲染失败，请查看 render.stderr.log")
    metadata = json.loads(
        await run_process(
            [
                tool("ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of",
                "json",
                str(output),
            ]
        )
    )
    video = next((stream for stream in metadata["streams"] if stream["codec_type"] == "video"), None)
    if not video or min(video["width"], video["height"]) < 1080:
        raise ValidationError("动画输出需要完整 1080p 画面")
    return output
