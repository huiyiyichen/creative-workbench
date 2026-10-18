"""Agent Skills discovery — expose 创意工作台 as an installable skill.

Implements the Agent Skills discovery protocol (RFC: cloudflare/agent-skills-
discovery-rfc) so external agents can install the read-skill via:

    npx skills add https://<your-workbench-host>

The CLI fetches ``/.well-known/agent-skills/index.json`` to discover skills,
then downloads each skill's ``SKILL.md``. All endpoints here are PUBLIC (no
Bearer token) because the discovery + skill download must precede auth — the
skill itself tells the agent to read ``$CREATIVE_WORKBENCH_API_URL`` before calling
the protected ``/api/v1/skill/*`` read endpoints.

Three public endpoints:
  GET /.well-known/agent-skills/index.json
  GET /.well-known/agent-skills/creative-workbench-reader/SKILL.md
  GET /skill/install  (human-readable install instructions for the profile UI)
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="", tags=["agent-skills"])

SKILL_NAME = "creative-workbench-reader"
SKILL_DESCRIPTION = (
    "读取创意工作台选题数据（今日精选 / 日报 / 趋势）。当用户询问"
    "「今天有什么值得写的选题」「最近有什么热点」「给我看看选题日报」时调用。"
    "可设置环境变量 CREATIVE_WORKBENCH_API_URL 指向本机实例。"
)


def _skill_markdown(base_url: str) -> str:
    """Render the SKILL.md body with the instance's base URL baked in.

    The agent reads ``$CREATIVE_WORKBENCH_API_URL`` at runtime,
    but we surface the discovered base URL in the docs so the user knows what
    to export. The skill is the same across instances; only the doc hint changes.
    """
    return f"""---
name: {SKILL_NAME}
description: {SKILL_DESCRIPTION}
version: 1.0.0
---

# 创意工作台 Reader — 选题数据读取

通过 HTTP API 读取创意工作台已抓取、已分析、已精选的选题数据。创意工作台是一个内容
选题雷达，持续抓取多个信源并用 6 维评分模型筛选高价值选题。

## 环境变量

创意工作台是本机单用户应用，接口只监听本机，不需要 Token：

```bash
export CREATIVE_WORKBENCH_API_URL="{base_url}"      # 当前创意工作台实例地址（本机）
```

> 若环境变量未设置，使用上面的默认地址；不要臆造其他地址。

## 端点

### 1. `GET $CREATIVE_WORKBENCH_API_URL/api/v1/skill/today-picks` — 今日精选选题

返回最近 N 小时内创意工作台的精选选题。**回答"今天有什么值得写的"的首选端点。**

参数：`hours`（1–168，默认 48）、`limit`（1–100，默认 20）、`category`（可选，如 `AI`）。

关键字段：
- `items[*].title` / `url` / `summary` — 标题、链接、摘要
- `items[*].analysis.adjusted_curation_score` — 最终排名分（越高越值得写）
- `items[*].analysis.recommended_reason` — AI 推荐理由
- `items[*].analysis.score_breakdown` — 完整评分明细

```bash
curl "$CREATIVE_WORKBENCH_API_URL/api/v1/skill/today-picks?hours=48&limit=10"
```

### 2. `GET $CREATIVE_WORKBENCH_API_URL/api/v1/skill/daily-report` — 日报

返回创意工作台生成的日报（已编辑的选题综述）。参数：`date`（YYYY-MM-DD，缺省=今天）。

关键字段：`overview`（综述段落）、`takeaway`（要点）、`top_picks`（精选条目）、
`keywords` / `trends`。

```bash
curl "$CREATIVE_WORKBENCH_API_URL/api/v1/skill/daily-report?date=2026-07-17"
```

### 3. `GET $CREATIVE_WORKBENCH_API_URL/api/v1/skill/trends` — 话题趋势 + 关键词

合并返回话题趋势和关键词词频。参数：`days`（1–30，默认 7）、`limit`（10–200，默认 50）。

```bash
curl "$CREATIVE_WORKBENCH_API_URL/api/v1/skill/trends?days=7"
```

## 典型用法

| 用户问题 | 调用 |
|---|---|
| 「今天有什么值得写的选题？」 | `GET /api/v1/skill/today-picks?hours=48&limit=10` → 按 `adjusted_curation_score` 解读 |
| 「给我看一下今天的选题日报」 | `GET /api/v1/skill/daily-report` |
| 「最近一周有什么热点趋势？」 | `GET /api/v1/skill/trends?days=7` |
| 「AI 领域最近有什么好选题？」 | `GET /api/v1/skill/today-picks?category=AI` |

## 输出规范

- 每条选题展示：标题、来源、`adjusted_curation_score`、`recommended_reason`、链接
- 多条时按分数降序，标注 Top N
- 引用原文时附 `url`，不要编造未返回的选题
- 无数据时如实说明"当前时间窗暂无精选"，不臆造
"""


def _skill_digest(markdown: str) -> str:
    """Stable sha256 digest of the skill markdown (for the index)."""
    return "sha256:" + hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def _base_url(request: Request) -> str:
    """Derive the public base URL from the incoming request.

    Uses the Host header (respects x-forwarded-host / proxy). Falls back to
    a configured override via settings if present.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto")
    proto = forwarded_proto or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost"
    return f"{proto}://{host}"


@router.get(
    "/.well-known/agent-skills/index.json",
    summary="Agent Skills discovery index",
)
async def agent_skills_index(request: Request):
    """Discovery index per the Agent Skills well-known URI protocol."""
    base_url = _base_url(request)
    skill_url = f"{base_url}/.well-known/agent-skills/{SKILL_NAME}/SKILL.md"
    return {
        "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
        "skills": [
            {
                "name": SKILL_NAME,
                "type": "skill-md",
                "description": SKILL_DESCRIPTION,
                "url": skill_url,
                "digest": _skill_digest(_skill_markdown(base_url)),
            }
        ],
    }


@router.get(
    "/.well-known/agent-skills/creative-workbench-reader/SKILL.md",
    summary="Creative Workbench reader skill (SKILL.md)",
)
async def agent_skill_markdown(request: Request) -> PlainTextResponse:
    """The skill instructions, with this instance's base URL baked in."""
    base_url = _base_url(request)
    return PlainTextResponse(_skill_markdown(base_url), media_type="text/markdown; charset=utf-8")
