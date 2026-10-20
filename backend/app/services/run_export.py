"""运行记录导出为 Markdown（改造方案 2.3）：流程、步骤、花费、关键决定、产物与出处。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

STATUS = {
    "queued": "排队",
    "running": "运行中",
    "waiting": "等待处理",
    "paused": "已暂停",
    "done": "完成",
    "failed": "失败",
    "stopped": "已停止",
    "reused": "复用",
}


def _t(v: Any) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v or "")[:19].replace("T", " ")


def _src(s: dict[str, Any]) -> str:
    title = s.get("title") or s.get("url") or ""
    if s.get("type") == "content":
        return f"采集内容 #{s.get('id')} {title}".strip()
    if s.get("type") == "library":
        return f"灵感库 #{s.get('id')} {title}".strip()
    return f"[{title}]({s.get('url')})" if s.get("url") else title


def run_markdown(data: dict[str, Any]) -> str:
    run = data["run"]
    lines = [
        f"# {run['title']}",
        "",
        f"- 流程：{run['flow_key']} v{run['flow_version']}",
        f"- 状态：{STATUS.get(run['status'], run['status'])}"
        + (f"（{run['status_reason']}）" if run.get("status_reason") else ""),
        f"- 开始：{_t(run.get('started_at'))}　结束：{_t(run.get('finished_at'))}",
        f"- 花费：¥{run.get('cost') or 0:.4f}　token：{run.get('input_tokens', 0)} / {run.get('output_tokens', 0)}",
    ]
    if run.get("parent_run_id"):
        lines.append(f"- 分叉自运行 #{run['parent_run_id']}，从「{run.get('fork_node')}」重跑")
    lines += ["", "## 步骤", "", "| 节点 | 分支 | 状态 | 尝试 | 耗时 | 花费 |", "|---|---|---|---|---|---|"]
    for s in data.get("steps") or []:
        dur = f"{(s.get('duration_ms') or 0) / 1000:.1f}s" if s.get("duration_ms") is not None else ""
        lines.append(
            f"| {s['label']} | {s.get('branch') or ''} | {STATUS.get(s['status'], s['status'])} | {s['attempt']} | {dur} | ¥{s.get('cost') or 0:.4f} |"
        )
    if data.get("decisions"):
        lines += ["", "## 人工决定", ""]
        for d in data["decisions"]:
            c = d.get("choice") or {}
            lines.append(
                f"- {d['gate']}：{c.get('title') or c.get('custom') or c}"
                + (f"（{d['note']}）" if d.get("note") else "")
            )
    lines += ["", "## 产物", ""]
    for a in data.get("artifacts") or []:
        content = a.get("content") or {}
        lines += [f"### {a['title']}", ""]
        if content.get("summary"):
            lines += [content["summary"], ""]
        for f in content.get("findings") or []:
            srcs = "；".join(_src(s) for s in f.get("sources") or [])
            lines.append(f"- **{f['id']}** {f['claim']}" + (f" —— {srcs}" if srcs else ""))
        for c in content.get("cards") or []:
            lines.append(
                f"- **{c['title']}**（{c.get('angle') or ''}）{c.get('why_now') or ''}　依据：{', '.join(c.get('refs') or [])}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
