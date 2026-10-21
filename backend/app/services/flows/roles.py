"""内部执行者的角色（改造方案 2.2）：研究员、汇总、策划。

角色之间不直接对话，只通过产物交接：每个角色读输入产物，产出新的产物（带来源关系）。
模型调用沿用现有模型层（路由、密钥、计费、预算），在 ``llm_call_context`` 里调用，自动记入运行与步骤。
工具调用只走工作台工具（``workbench_tools.call_tool``），自动写入调用树。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.library import LibraryItem
from app.services import prompt_kit, workbench_tools as wt
from app.services.flows.spec import NodeSpec

PLATFORM_LABEL = {
    "library": "灵感库",
    "bilibili": "B站",
    "youtube": "YouTube",
    "hn": "Hacker News",
    "reddit": "Reddit",
    "github": "GitHub",
    "web": "网页",
}
# 研究员按分工能用的工具（只读）
BRANCH_TOOLS = {
    "library": ["search_library", "search_content", "read_content"],
    "web": ["fetch_url", "search_content", "read_content"],
}
PLATFORM_TOOLS = ["search_content", "platform_search", "read_content"]


class RoleError(Exception):
    pass


@dataclass
class RoleContext:
    db: AsyncSession
    run_id: int
    step_id: int
    node: NodeSpec
    inputs: dict[str, Any]
    branch: str | None = None
    input_artifacts: list[dict[str, Any]] = field(default_factory=list)
    override: dict[str, Any] = field(default_factory=dict)
    decisions: dict[str, Any] = field(default_factory=dict)
    round: int = 1
    executor: str = "internal"
    summary: str | None = None  # 没有产物时的步骤摘要

    def latest(self, kind: str) -> dict[str, Any] | None:
        return next((a for a in reversed(self.input_artifacts) if a["kind"] == kind), None)

    @property
    def routing_group(self) -> str:
        return self.override.get("routing_group") or self.node.routing_group

    def system_extra(self) -> str:
        extra = (self.override.get("prompt_extra") or "").strip()
        return f"\n\n额外要求（来自重跑设置）：{extra}" if extra else ""


@dataclass
class ArtifactOut:
    kind: str
    title: str
    content: dict[str, Any]
    links: list[dict[str, Any]] = field(default_factory=list)


async def _llm(ctx: RoleContext, messages: list[dict[str, str]], *, scene: str, max_tokens: int = 1800) -> Any:
    from app.services.llm import provider
    from app.services.llm.call_context import llm_call_context

    with llm_call_context(run_id=str(ctx.run_id), step_id=str(ctx.step_id)):
        return await provider.call_llm_json(
            messages, temperature=0.3, max_tokens=max_tokens, scene=scene, routing_group=ctx.routing_group
        )


def _tool_doc(names: list[str]) -> str:
    lines = []
    for t in wt.describe_tools(frozenset(names)):
        props = t["inputSchema"].get("properties", {})
        args = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in props.items())
        lines.append(f"- {t['name']}({args})：{t['description']}")
    return "\n".join(lines)


def _source_key(s: dict[str, Any]) -> tuple:
    return (s.get("type"), s.get("id"), s.get("url"))


async def validate_sources(db: AsyncSession, sources: list[Any]) -> list[dict[str, Any]]:
    """只保留真实存在的出处：采集内容 id、灵感库 id、http(s) 链接。"""
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        typ = s.get("type")
        src: dict[str, Any] | None = None
        if typ == "content" and str(s.get("id") or "").isdigit():
            c = await db.get(ContentItem, int(s["id"]))
            if c:
                src = {"type": "content", "id": c.id, "title": c.title, "url": c.url}
        elif typ == "library" and str(s.get("id") or "").isdigit():
            li = await db.get(LibraryItem, int(s["id"]))
            if li:
                src = {"type": "library", "id": li.id, "title": li.title, "url": li.url}
        elif typ == "url" and re.match(r"^https?://", str(s.get("url") or "")):
            src = {"type": "url", "url": str(s["url"])[:1000], "title": str(s.get("title") or "")[:200] or None}
        if src and _source_key(src) not in seen:
            seen.add(_source_key(src))
            out.append(src)
    return out


def _cite_links(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links = []
    for f in findings:
        for s in f.get("sources") or []:
            links.append(
                {
                    "relation": "cites",
                    "target_type": s["type"],
                    "target_id": s.get("id"),
                    "target_url": s.get("url") if s["type"] == "url" else None,
                    "anchor": f["id"],
                }
            )
    return links


async def _seed_text(ctx: RoleContext) -> str:
    ids = [int(i) for i in ctx.inputs.get("content_ids") or [] if str(i).isdigit()][:8]
    if not ids:
        return ""
    rows = (await ctx.db.execute(select(ContentItem).where(ContentItem.id.in_(ids)))).scalars().all()
    return "\n".join(f"- 内容 #{c.id}：{c.title}（{c.platform or ''}）" for c in rows)


# ── 研究员 ──


async def researcher(ctx: RoleContext) -> list[ArtifactOut]:
    branch = ctx.branch or "library"
    tools = BRANCH_TOOLS.get(branch, PLATFORM_TOOLS)
    max_calls = int(ctx.node.params.get("max_tool_calls") or 6)
    topic = str(ctx.inputs.get("topic") or "").strip()
    label = PLATFORM_LABEL.get(branch, branch)
    scope = (
        f"你负责「{label}」：用 search_content 时传 platform={branch}，用 platform_search 时也传 platform={branch}。"
        if tools is PLATFORM_TOOLS
        else f"你负责「{label}」。"
    )
    seed = await _seed_text(ctx)
    system = (
        "你是创意工作台的研究员，为一个内容选题做调研。只能通过工具获取信息，不能编造。\n" + prompt_kit.UNTRUSTED + "\n"
        f"{scope}\n可用工具：\n{_tool_doc(tools)}\n\n"
        "每一轮只输出一个 JSON：\n"
        '调用工具：{"action": "tool", "tool": "工具名", "args": {...}, "why": "为什么调用"}\n'
        '结束：{"action": "final", "summary": "一两句总体判断", "findings": [{"claim": "结论", '
        '"sources": [{"type": "content", "id": 123} 或 {"type": "library", "id": 45} 或 '
        '{"type": "url", "url": "https://…", "title": "…"}]}]}\n'
        f"最多调用 {max_calls} 次工具。每条结论必须带出处（工具结果里出现过的 content_id / library_id / url），"
        "没有出处的结论不要写。结论 3 到 6 条，写清楚事实、数据和时间；保留来源原本的确定程度和相对时间，不要强化。"
        + ctx.system_extra()
    )
    user = f"运行 #{ctx.run_id}\n选题：{topic}"
    if ctx.inputs.get("notes"):
        user += f"\n补充要求：{ctx.inputs['notes']}"
    if seed:
        user += f"\n起点内容（可用 read_content 读取）：\n{seed}"
    messages: list[dict[str, str]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    tool_ctx = wt.ToolContext(run_id=ctx.run_id, step_id=ctx.step_id, allowed=frozenset(tools))
    calls = 0
    final: dict[str, Any] | None = None
    for _ in range(max_calls + 2):
        reply = await _llm(ctx, messages, scene="flow_researcher")
        if not isinstance(reply, dict):
            raise RoleError("研究员没有返回 JSON 对象")
        messages.append({"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)})
        if reply.get("action") == "tool" and calls < max_calls:
            calls += 1
            name = str(reply.get("tool") or "")
            try:
                result: Any = await wt.call_tool(ctx.db, name, reply.get("args") or {}, tool_ctx)
            except wt.ToolError as exc:
                result = {"error": str(exc)}
            text = json.dumps(result, ensure_ascii=False, default=str)
            if len(text) > 3500:
                text = text[:3500] + "…（截断）"
            left = max_calls - calls
            messages.append(
                {
                    "role": "user",
                    "content": f"工具 {name} 的结果：\n{text}\n\n还可以调用 {left} 次工具。"
                    + ("现在请输出 final。" if left == 0 else ""),
                }
            )
            continue
        if reply.get("action") == "final":
            final = reply
            break
        messages.append({"role": "user", "content": "工具次数已用完或格式不对，请直接输出 final JSON。"})
    if final is None:
        raise RoleError("研究员没有给出最终结论")
    findings = []
    for f in final.get("findings") or []:
        if not isinstance(f, dict) or not str(f.get("claim") or "").strip():
            continue
        sources = await validate_sources(ctx.db, f.get("sources") or [])
        if not sources:  # 每条结论必须带出处
            continue
        findings.append({"id": f"f{len(findings) + 1}", "claim": str(f["claim"]).strip(), "sources": sources})
    content = {
        "branch": branch,
        "branch_label": label,
        "topic": topic,
        "summary": str(final.get("summary") or "").strip(),
        "findings": findings,
        "tool_calls": calls,
        "dropped": len(final.get("findings") or []) - len(findings),
    }
    return [ArtifactOut("research_brief", f"研究简报 · {label}", content, _cite_links(findings))]


# ── 汇总 ──


async def aggregator(ctx: RoleContext) -> list[ArtifactOut]:
    briefs = [a for a in ctx.input_artifacts if a["kind"] == "research_brief"]
    refs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    lines = []
    for b in briefs:
        c = b.get("content") or {}
        lines.append(f"## {c.get('branch_label') or b['title']}（简报 {b['id']}）\n{c.get('summary') or ''}")
        for f in c.get("findings") or []:
            key = f"b{b['id']}.{f['id']}"
            refs[key] = (b, f)
            src = "；".join(s.get("title") or s.get("url") or "" for s in f.get("sources") or [])
            lines.append(f"- [{key}] {f['claim']}（出处：{src}）")
    topic = str(ctx.inputs.get("topic") or "")
    if not refs:
        content = {
            "topic": topic,
            "summary": "各平台研究员都没有找到带出处的结论。",
            "findings": [],
            "branches": [b["id"] for b in briefs],
        }
        links = [{"relation": "derived_from", "target_type": "artifact", "target_id": b["id"]} for b in briefs]
        return [ArtifactOut("research_brief", "研究简报 · 汇总", content, links)]
    system = (
        "你是研究汇总。把多个平台的研究简报合并成一份：去重、合并相同结论、标出分歧，按重要性排序。"
        "每条结论必须引用方括号里的条目编号（可以多个），不能写没有编号支撑的结论。\n"
        '只输出 JSON：{"summary": "三五句总体判断", "findings": [{"claim": "结论", "refs": ["b12.f1", "b13.f2"]}]}'
        + ctx.system_extra()
    )
    reply = await _llm(
        ctx,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"运行 #{ctx.run_id}\n选题：{topic}\n\n" + "\n".join(lines)},
        ],
        scene="flow_aggregator",
        max_tokens=3000,
    )
    if not isinstance(reply, dict):
        raise RoleError("汇总没有返回 JSON 对象")
    findings = []
    links: list[dict[str, Any]] = [
        {"relation": "derived_from", "target_type": "artifact", "target_id": b["id"]} for b in briefs
    ]
    for f in reply.get("findings") or []:
        if not isinstance(f, dict) or not str(f.get("claim") or "").strip():
            continue
        used = [r for r in f.get("refs") or [] if r in refs]
        if not used:
            continue
        fid = f"f{len(findings) + 1}"
        sources: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        for r in used:
            b, orig = refs[r]
            links.append(
                {
                    "relation": "cites",
                    "target_type": "artifact",
                    "target_id": b["id"],
                    "anchor": fid,
                    "target_anchor": orig["id"],
                }
            )
            for s in orig.get("sources") or []:
                if _source_key(s) not in seen:
                    seen.add(_source_key(s))
                    sources.append(s)
        findings.append({"id": fid, "claim": str(f["claim"]).strip(), "refs": used, "sources": sources})
    content = {
        "topic": topic,
        "summary": str(reply.get("summary") or "").strip(),
        "findings": findings,
        "branches": [b["id"] for b in briefs],
    }
    return [ArtifactOut("research_brief", "研究简报 · 汇总", content, links)]


# ── 策划 ──


async def planner(ctx: RoleContext) -> list[ArtifactOut]:
    brief = next((a for a in reversed(ctx.input_artifacts) if a["kind"] == "research_brief"), None)
    if brief is None:
        raise RoleError("没有研究简报可用")
    c = brief.get("content") or {}
    n = int(ctx.node.params.get("directions") or 3)
    topic = str(ctx.inputs.get("topic") or "")
    fids = {f["id"] for f in c.get("findings") or []}
    lines = [f"- [{f['id']}] {f['claim']}" for f in c.get("findings") or []]
    system = (
        f"你是资深内容策划。根据研究简报给出 {n} 个不同的选题方向，切入角度要明显不同（例如解读、实测、观点、盘点、教程）。\n"
        "<how_to_judge>每个方向先过三项检查：有趣（有悬念或反常识）、有信息量（读者能学到东西）、有共鸣（和读者自己的处境有关），"
        "至少占两项才给出；简报证据薄或原选题站不住时，不要返回空，改成证据撑得住的角度（例如方法论、怎么识别、通用套路），照样给满。写清这件事和谁有关、他看完能得到什么。只判断内容本身的条件，不预测播放量或阅读量。"
        "借鉴爆款只借结构（钩子类型、骨架、互动方式），不复用原句。</how_to_judge>\n"
        "每个方向说明：标题示例、角度、目标读者与「和他有什么关系」、为什么现在做、适合的形式（article 文章 / video 视频 / image 图文）、"
        "hkr（有趣 / 信息量 / 共鸣 三项各 0–2 分）、needs（作者还需要补的亲历或数据，最多 2 项，没有就空数组），并引用支撑它的简报条目编号。\n"
        '只输出 JSON：{"cards": [{"title": "…", "angle": "…", "audience": "…", "why_now": "…", "format": "video", '
        '"hkr": {"h": 2, "k": 1, "r": 2}, "needs": ["…"], "refs": ["f1"]}]}' + prompt_kit.UNTRUSTED + ctx.system_extra()
    )
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"运行 #{ctx.run_id}\n选题：{topic}\n总体判断：{c.get('summary') or ''}\n\n简报条目：\n"
            + ("\n".join(lines) or "（无）"),
        },
    ]
    raw_cards = _planner_cards(await _llm(ctx, messages, scene="flow_planner", max_tokens=3500))
    if not raw_cards:
        # 模型常在证据薄时返回空数组或换了键名：明确要求再给一次
        retry = messages + [
            {
                "role": "user",
                "content": f"上一次没有给出可用的方向。请务必输出 {n} 个方向，键名用 cards，每个都要有 title；"
                "原选题证据不足就换成简报撑得住的角度。只输出 JSON。",
            }
        ]
        raw_cards = _planner_cards(await _llm(ctx, retry, scene="flow_planner", max_tokens=3500))
    cards = []
    links: list[dict[str, Any]] = [{"relation": "derived_from", "target_type": "artifact", "target_id": brief["id"]}]
    for card in raw_cards:
        did = f"d{len(cards) + 1}"
        used = [r for r in card.get("refs") or [] if r in fids]
        cards.append(
            {
                "id": did,
                "title": str(card["title"]).strip(),
                "angle": str(card.get("angle") or "").strip(),
                "why_now": str(card.get("why_now") or "").strip(),
                "format": str(card.get("format") or "").strip() or None,
                "audience": str(card.get("audience") or "").strip()[:200] or None,
                "hkr": _hkr(card.get("hkr")),
                "needs": [str(x).strip()[:120] for x in (card.get("needs") or []) if str(x).strip()][:2],
                "refs": used,
            }
        )
        for r in used:
            links.append(
                {
                    "relation": "cites",
                    "target_type": "artifact",
                    "target_id": brief["id"],
                    "anchor": did,
                    "target_anchor": r,
                }
            )
        if len(cards) >= n:
            break
    if not cards:
        raise RoleError("策划没有给出可用的方向")
    return [ArtifactOut("direction_cards", f"方向卡 · {topic}"[:300], {"topic": topic, "cards": cards}, links)]


_CARD_LIST_KEYS = ("cards", "directions", "items", "topics", "方向", "选题")
_CARD_TITLE_KEYS = ("title", "标题", "headline", "name", "标题示例")


def _planner_cards(reply: Any) -> list[dict[str, Any]]:
    """容忍模型的常见偏差：顶层直接是数组、换了列表键名、标题用了别的键。"""
    items: Any = reply
    if isinstance(reply, dict):
        items = next((reply[k] for k in _CARD_LIST_KEYS if isinstance(reply.get(k), list)), None)
        if items is None:
            items = next((v for v in reply.values() if isinstance(v, list) and v and isinstance(v[0], dict)), [])
    if not isinstance(items, list):
        return []
    out = []
    for card in items:
        if not isinstance(card, dict):
            continue
        title = next((str(card[k]).strip() for k in _CARD_TITLE_KEYS if str(card.get(k) or "").strip()), "")
        if title:
            out.append({**card, "title": title})
    return out


def _hkr(raw: Any) -> dict[str, int] | None:
    """策划给的 HKR 三项分（各 0–2），缺项或不是数字时返回 None。"""
    if not isinstance(raw, dict):
        return None
    out: dict[str, int] = {}
    for k in ("h", "k", "r"):
        v = raw.get(k)
        if not isinstance(v, int | float) or isinstance(v, bool):
            return None
        out[k] = max(0, min(2, int(v)))
    return out


ROLE_IMPLS: dict[str, Any] = {"researcher": researcher, "aggregator": aggregator, "planner": planner}


def _register_creative_roles() -> None:
    from app.services.flows import roles_draft, roles_platform, roles_video

    ROLE_IMPLS.update(roles_draft.ROLES)
    ROLE_IMPLS.update(roles_platform.ROLES)
    ROLE_IMPLS.update(roles_video.ROLES)


_register_creative_roles()
