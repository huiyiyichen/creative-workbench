"""制作这一步的外部执行者（创作工作台设计 6.2、12「agent_adapters」）。

三个执行者都在产出物的工作目录里交付动画源码（src/Scenes.tsx + design.ready.json），由工作台编译、渲染：

* ``deepseek_harness``：本机 DeepSeek Harness（dsh），沿用 studio_remotion.design_animation。
* ``claude_code``：Claude Code 无头模式 ``claude -p … --output-format stream-json --verbose``。
* ``codex``：``codex exec --json``。

外部 agent 的事件逐行解析，统一转换成 ``{kind, name, summary, detail}``（message / tool_call / tool_result /
command / file_change / usage / error），写进运行的调用树（trace_spans，via=执行者）。
执行者只拿到工作目录里的冻结合同与反馈，不拿模型 Key、后端配置或任意路径。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.core.exceptions import ValidationError

VIA = {"deepseek_harness": "dsh", "claude_code": "claude", "codex": "codex"}  # trace_spans.via 最长 10
EXECUTOR_LABEL = {"deepseek_harness": "DeepSeek Harness", "claude_code": "Claude Code", "codex": "Codex"}
DESIGN_TIMEOUT = 600  # 秒
FEEDBACK_NOTE = (
    "如果当前目录有 qa_feedback.json，那是上一版成片的质检问题：在已有 src/Scenes.tsx 上逐条修正，"
    "不要推倒重来；有 keyframes.json 时把它当作每个分镜的关键帧画面参考。"
)


def design_prompt() -> str:
    from app.services.studio_remotion import DESIGN_PROMPT

    return DESIGN_PROMPT + FEEDBACK_NOTE


# ── 可用性 ──


def cli_path(executor: str) -> str | None:
    env = {"claude_code": "CLAUDE_CODE_CLI", "codex": "CODEX_CLI", "deepseek_harness": "DSH_CLI"}[executor]
    name = {"claude_code": "claude", "codex": "codex", "deepseek_harness": "dsh"}[executor]
    return os.environ.get(env) or shutil.which(name)


def missing(executor: str) -> str | None:
    if executor not in EXECUTOR_LABEL:
        return f"未知的执行者 {executor}"
    if not cli_path(executor):
        hint = {
            "deepseek_harness": "请安装本机 DeepSeek Harness（dsh）",
            "claude_code": "请安装 Claude Code（npm i -g @anthropic-ai/claude-code）并登录",
            "codex": "请安装 Codex CLI（npm i -g @openai/codex）并登录",
        }[executor]
        return hint
    return None


def status() -> list[dict[str, Any]]:
    return [
        {"key": k, "label": v, "available": missing(k) is None, "hint": missing(k)} for k, v in EXECUTOR_LABEL.items()
    ]


# ── 事件转换（纯函数） ──


def _short(value: Any, n: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def convert_claude(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Claude Code stream-json 一行 → 统一事件。"""
    typ = event.get("type")
    out: list[dict[str, Any]] = []
    if typ == "assistant":
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                out.append({"kind": "message", "name": "assistant", "summary": _short(block["text"]), "detail": block})
            elif block.get("type") == "tool_use":
                name = str(block.get("name") or "tool")
                args = block.get("input") or {}
                kind = (
                    "file_change"
                    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit")
                    else ("command" if name == "Bash" else "tool_call")
                )
                target = args.get("file_path") or args.get("command") or args.get("pattern") or args
                out.append(
                    {"kind": kind, "name": name, "summary": _short(target), "detail": block, "id": block.get("id")}
                )
    elif typ == "user":
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                content = block.get("content")
                if isinstance(content, list):
                    content = " ".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
                out.append(
                    {
                        "kind": "error" if block.get("is_error") else "tool_result",
                        "name": "tool_result",
                        "summary": _short(content or ""),
                        "detail": block,
                        "id": block.get("tool_use_id"),
                    }
                )
    elif typ == "result":
        usage = event.get("usage") or {}
        out.append(
            {
                "kind": "error" if event.get("is_error") else "usage",
                "name": "result",
                "summary": _short(event.get("result") or event.get("subtype") or ""),
                "detail": {
                    "cost_usd": event.get("total_cost_usd"),
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "num_turns": event.get("num_turns"),
                    "duration_ms": event.get("duration_ms"),
                },
            }
        )
    elif typ == "system" and event.get("subtype") == "init":
        out.append(
            {"kind": "message", "name": "init", "summary": _short(event.get("model") or "session"), "detail": {}}
        )
    return out


def convert_codex(event: dict[str, Any]) -> list[dict[str, Any]]:
    """codex exec --json 一行 → 统一事件。"""
    typ = event.get("type") or ""
    if typ == "turn.completed":
        usage = event.get("usage") or {}
        return [
            {
                "kind": "usage",
                "name": "turn",
                "summary": f"输入 {usage.get('input_tokens', 0)} / 输出 {usage.get('output_tokens', 0)} token",
                "detail": usage,
            }
        ]
    if typ in ("turn.failed", "error"):
        err = event.get("error") or event
        return [{"kind": "error", "name": "error", "summary": _short(err.get("message") or err), "detail": event}]
    if typ != "item.completed":
        return []
    item = event.get("item") or {}
    it = item.get("type") or item.get("item_type")
    if it in ("agent_message", "assistant_message"):
        return [{"kind": "message", "name": "assistant", "summary": _short(item.get("text") or ""), "detail": item}]
    if it == "command_execution":
        code = item.get("exit_code")
        return [
            {
                "kind": "error" if code not in (0, None) else "command",
                "name": "shell",
                "summary": _short(f"{item.get('command')} → {code}"),
                "detail": item,
            }
        ]
    if it == "file_change":
        files = ", ".join(str(c.get("path")) for c in item.get("changes") or [])
        return [{"kind": "file_change", "name": "patch", "summary": _short(files or "文件修改"), "detail": item}]
    if it == "mcp_tool_call":
        return [
            {
                "kind": "tool_call",
                "name": str(item.get("tool") or "mcp"),
                "summary": _short(item.get("arguments") or ""),
                "detail": item,
            }
        ]
    if it == "reasoning":
        return [{"kind": "message", "name": "reasoning", "summary": _short(item.get("text") or ""), "detail": item}]
    return [{"kind": "tool_call", "name": str(it or "item"), "summary": _short(item), "detail": item}]


CONVERTERS = {"claude_code": convert_claude, "codex": convert_codex}


def command(executor: str, workspace: Path, prompt: str) -> list[str]:
    cli = cli_path(executor)
    if not cli:
        raise ValidationError(missing(executor) or "执行者不可用")
    if executor == "claude_code":
        return [
            cli,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Read,Write,Edit,MultiEdit,Glob,Grep,Bash(npx tsc:*),Bash(node:*)",
        ]
    if executor == "codex":
        return [
            cli,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-C",
            str(workspace),
            prompt,
        ]
    raise ValidationError(f"执行者 {executor} 不走命令行事件流")


# ── 运行 ──

EventSink = Callable[[dict[str, Any]], Awaitable[None]]


async def run_agent(
    executor: str,
    workspace: Path,
    on_stage: Callable[..., Awaitable[None]],
    sink: EventSink | None = None,
    *,
    timeout: float = DESIGN_TIMEOUT,
    argv: list[str] | None = None,
) -> dict[str, Any]:
    """启动外部 agent，逐行转换事件；交付 design.ready.json（或 Scenes.tsx 且正常退出）即完成。"""
    label = EXECUTOR_LABEL.get(executor, executor)
    args = argv or command(executor, workspace, design_prompt())
    convert = CONVERTERS[executor]
    ready = workspace / "design.ready.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DATABASE_", "INTEGRATION_SECRET"))}
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=workspace,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        limit=8 * 1024 * 1024,
    )
    started = time.monotonic()
    counts: dict[str, int] = {}
    log = (workspace / f"{executor}.events.jsonl").open("w", encoding="utf-8")
    stderr_task = asyncio.create_task(proc.stderr.read())
    try:
        async with asyncio.timeout(timeout):
            while line := await proc.stdout.readline():
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                log.write(raw + "\n")
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                for ev in convert(event):
                    counts[ev["kind"]] = counts.get(ev["kind"], 0) + 1
                    if sink:
                        await sink(ev)
                await on_stage(f"{label} 设计动画")
            code = await proc.wait()
    except TimeoutError as exc:
        raise ValidationError(
            f"{label} 设计超过 {int(timeout // 60)} 分钟，已停止。可重试，已生成的源码会复用"
        ) from exc
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        log.close()
        err = await stderr_task if stderr_task.done() or proc.returncode is not None else b""
        (workspace / f"{executor}.stderr.log").write_bytes(err or b"")
    scenes = workspace / "src" / "Scenes.tsx"
    if not ready.is_file():
        if code == 0 and scenes.is_file():
            ready.write_text('{"entry":"src/Scenes.tsx"}', encoding="utf-8")
        else:
            raise ValidationError(f"{label} 没有交付动画源码（退出码 {code}），请查看 {executor}.stderr.log")
    return {"exit_code": code, "events": counts, "seconds": int(time.monotonic() - started)}


async def design(executor: str, workspace: Path, on_stage, *, job: Any = None) -> dict[str, Any]:
    """制作的「设计」阶段：按执行者交付 src/Scenes.tsx。事件写进运行调用树。"""
    if executor == "deepseek_harness":
        from app.services.studio_remotion import design_animation

        # dsh 读当前目录的 AGENTS.md；把质检反馈说明追加进去
        agents = workspace / "AGENTS.md"
        if agents.is_file() and (workspace / "qa_feedback.json").is_file():
            agents.write_text(agents.read_text(encoding="utf-8") + "\n" + FEEDBACK_NOTE + "\n", encoding="utf-8")
        await design_animation(workspace, on_stage)
        await _record(
            job, executor, {"kind": "message", "name": "dsh", "summary": "DeepSeek Harness 交付设计源码", "detail": {}}
        )
        return {"executor": executor}
    if executor not in CONVERTERS:
        raise ValidationError(f"未知的执行者 {executor}")

    async def sink(ev: dict[str, Any]) -> None:
        await _record(job, executor, ev)

    return await run_agent(executor, workspace, on_stage, sink)


async def _record(job: Any, executor: str, ev: dict[str, Any]) -> None:
    """外部 agent 事件 → trace_spans（kind=agent_event，via=执行者），挂在制作步骤下。"""
    if job is None or not getattr(job, "run_id", None):
        return
    from app.services import trace_service

    async with trace_service.span(
        job.db,
        kind="agent_event",
        name=f"{ev['kind']}:{ev.get('name') or ''}"[:100],
        run_id=job.run_id,
        step_id=job.step_id,
        attributes={"executor": executor, "event": ev["kind"]},
        payload={"event": ev.get("detail")},
        via=VIA.get(executor, "agent"),
    ) as rec:
        rec["summary"] = ev.get("summary")
        rec["result"] = None
