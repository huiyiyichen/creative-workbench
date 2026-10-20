"""工作台工具第一批（改造方案 2.1 / 2.2）。

内部角色和外部 agent（经 MCP）都只通过这些工具读写工作台数据；每次调用写入调用树（``trace_spans``），
完整参数与结果脱敏压缩存 ``data/traces/``。

第一批：搜索灵感库、搜索采集内容、读取原文 / 字幕 / 评论、平台搜索（即时追踪词搜索）、抓取网页、加入收藏、记随笔。
创建项目、提交文稿修改建议、生图、渲染视频在阶段 4 加入。
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import WorkbenchToken
from app.models.content import ContentItem
from app.services import trace_service

TEXT_LIMIT = 6000


class ToolError(Exception):
    pass


class ToolDenied(ToolError):
    pass


@dataclass
class ToolContext:
    run_id: int | None = None
    step_id: int | None = None
    via: str = "flow"  # flow / mcp
    token_id: int | None = None
    allowed: frozenset[str] | None = None  # None = 全部
    project_ids: frozenset[int] | None = None  # None = 不限项目


@dataclass
class Tool:
    name: str
    title: str
    description: str
    schema: dict[str, Any]
    handler: Callable[[AsyncSession, dict[str, Any], ToolContext], Awaitable[Any]]
    writes: bool = False
    tags: list[str] = field(default_factory=list)


def _clip(text: str | None, limit: int = TEXT_LIMIT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + f"…（已截断，共 {len(text)} 字）"


def _content_brief(c: ContentItem) -> dict[str, Any]:
    return {
        "content_id": c.id,
        "title": c.title,
        "url": c.url,
        "platform": c.platform,
        "author": c.author,
        "published_at": c.published_at.isoformat() if c.published_at else None,
        "summary": _clip(c.summary, 400),
        "verdict": c.verdict,
    }


# ── 处理函数 ──


async def _search_library(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from app.services import library

    res = await library.list_items(
        db, q=args.get("query") or None, kind=args.get("kind") or None, limit=min(int(args.get("limit") or 10), 30)
    )
    return [
        {
            "library_id": it["id"],
            "kind": it.get("kind"),
            "title": it.get("title"),
            "url": it.get("url"),
            "content_id": it.get("content_id"),
            "tags": it.get("tags"),
            "platform": it.get("platform"),
            "notes": _clip(it.get("my_notes") or it.get("ai_description") or it.get("body"), 300),
        }
        for it in res.get("items", [])
    ]


async def _search_content(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ToolError("query 不能为空")
    stmt = select(ContentItem)
    for term in query.split()[:5]:
        like = f"%{term}%"
        stmt = stmt.where(or_(ContentItem.title.ilike(like), ContentItem.summary.ilike(like)))
    if args.get("platform"):
        stmt = stmt.where(ContentItem.platform == args["platform"])
    if args.get("days"):
        since = datetime.now(UTC) - timedelta(days=int(args["days"]))
        stmt = stmt.where(ContentItem.crawled_at >= since)
    stmt = stmt.order_by(ContentItem.published_at.desc().nulls_last(), ContentItem.id.desc()).limit(
        min(int(args.get("limit") or 10), 30)
    )
    return [_content_brief(c) for c in (await db.execute(stmt)).scalars()]


async def _read_content(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from app.services import comments

    cid = int(args.get("content_id") or 0)
    c = await db.get(ContentItem, cid)
    if c is None:
        raise ToolError(f"内容 {cid} 不存在")
    part = args.get("part") or "text"
    base = _content_brief(c)
    if part == "text":
        return {**base, "text": _clip(c.raw_content or c.summary)}
    if part == "comments":
        data = await comments.collect(db, cid)
        return {
            **base,
            "comment_state": data["state"],
            "comments": [
                {"comment_id": x["id"], "author": x["author"], "likes": x["likes"], "text": _clip(x["text"], 400)}
                for x in data["items"]
            ],
        }
    if part == "subtitles":
        src = comments.resolve_source(c)
        if src is None or src[0] not in ("bilibili", "youtube"):
            return {**base, "subtitles": None, "note": "这个来源没有字幕"}
        from app.services.platform_keys import get_platform_keys
        from app.services.platforms import NotSupported, PlatformError, get_adapter

        keys = await get_platform_keys(db)
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                tracks = await get_adapter(src[0], client, api_key=keys.get(src[0])).fetch_subtitles(src[1])
        except (NotSupported, PlatformError, httpx.HTTPError) as exc:
            return {**base, "subtitles": None, "note": f"字幕获取失败：{exc}"}
        if not tracks:
            return {**base, "subtitles": None, "note": "没有字幕"}
        t = tracks[0]
        return {**base, "subtitles": {"language": t.language, "text": _clip(t.text)}}
    raise ToolError("part 只能是 text / subtitles / comments")


async def _platform_search(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from app.services.platform_keys import get_platform_keys
    from app.services.platforms import NotSupported, PlatformError, get_adapter

    platform = str(args.get("platform") or "").lower()
    query = str(args.get("query") or "").strip()
    if not platform or not query:
        raise ToolError("platform 与 query 必填")
    keys = await get_platform_keys(db)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            entries = await get_adapter(platform, client, api_key=keys.get(platform)).search(
                query, limit=min(int(args.get("limit") or 8), 20)
            )
    except (NotSupported, PlatformError, httpx.HTTPError) as exc:
        raise ToolError(f"{platform} 搜索失败：{exc}") from exc
    return [
        {
            "title": e.get("title"),
            "url": e.get("url"),
            "author": e.get("author"),
            "published_at": e["published_at"].isoformat() if e.get("published_at") else None,
            "metrics": e.get("metrics"),
            "summary": _clip(e.get("summary"), 300),
        }
        for e in entries
    ]


async def _fetch_url(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from app.services.article_reader import _fetch_remote_article_tiered

    url = str(args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ToolError("url 必须以 http(s):// 开头")
    try:
        art, method = await _fetch_remote_article_tiered(url)
    except Exception as exc:  # noqa: BLE001 - 抓取失败原样告诉调用方
        raise ToolError(f"抓取失败：{exc}") from exc
    return {
        "url": art.canonical_url or url,
        "title": art.title,
        "published_at": art.published_at.isoformat() if art.published_at else None,
        "text": _clip(art.text_content),
    }


async def _add_favorite(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from app.services import library

    if args.get("content_id"):
        item = await library.add_from_content(db, int(args["content_id"]))
    elif args.get("url"):
        item = await library.add_from_link(db, str(args["url"]), note=args.get("note"))
    else:
        raise ToolError("content_id 或 url 至少给一个")
    return {"library_id": item.id, "title": item.title, "kind": item.kind}


async def _write_note(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from app.services import notes

    body = str(args.get("body") or "").strip()
    if not body:
        raise ToolError("body 不能为空")
    note = await notes.create_note(db, body, source="agent")
    return {"note_id": note.id, "created_at": note.created_at.isoformat()}


async def _scoped_output(db: AsyncSession, output_id: Any, ctx: ToolContext):
    from app.core.exceptions import AppException
    from app.services import project_service as ps

    try:
        output = await ps.get_output(db, int(output_id))
    except (TypeError, ValueError, AppException) as exc:
        raise ToolError("没有这个产出物") from exc
    if ctx.project_ids is not None and output.project_id not in ctx.project_ids:
        raise ToolDenied("令牌不允许访问这个项目")
    return output


async def _read_bundle(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from app.services import delivery_service, output_service, project_service as ps

    output = await _scoped_output(db, args.get("output_id"), ctx)
    if output.kind not in delivery_service.DELIVERABLE_KINDS:
        raise ToolError("这个产出物没有提示词包")
    data, _ctype, _name = await output_service.bundle(db, output.id, "md")
    return delivery_service.bundle_brief(await ps.output_view(db, output.id), data.decode("utf-8"))


async def _upload_output(db: AsyncSession, args: dict[str, Any], ctx: ToolContext) -> Any:
    from pathlib import Path

    from app.core.exceptions import AppException
    from app.services import delivery_service

    output = await _scoped_output(db, args.get("output_id"), ctx)
    note = str(args.get("note") or "") or None
    try:
        if args.get("path"):
            path = Path(str(args["path"])).expanduser()
            if not path.is_absolute():
                raise ToolError("path 需要是本机文件的绝对路径")
            res = await delivery_service.attach(db, output.id, path, filename=path.name, source="agent", note=note)
        elif args.get("url"):
            url = str(args["url"])
            if not url.startswith(("http://", "https://")):
                raise ToolError("url 需以 http(s):// 开头")
            res = await delivery_service.attach_from_url(db, output.id, url, note=note)
        else:
            raise ToolError("需要 path 或 url")
    except AppException as exc:
        raise ToolError(getattr(exc, "message", None) or str(exc)) from exc
    d = res["delivery"]
    return {"output_id": output.id, "artifact_id": d["artifact_id"], "duration": d["duration"], "size": d["size"]}


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "search_library",
            "搜索灵感库",
            "按关键词搜索灵感库（收藏的文章、视频、仓库、提示词、美术素材）。",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "关键词"},
                    "kind": {"type": "string", "description": "可选：article / video / repo / prompt / asset"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            _search_library,
        ),
        Tool(
            "search_content",
            "搜索采集内容",
            "在已采集的内容里按标题与摘要搜索，可按平台和最近天数筛选。",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "platform": {"type": "string", "description": "可选：bilibili / youtube / hn / reddit / github …"},
                    "days": {"type": "integer", "description": "可选：只看最近几天采集的"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            _search_content,
        ),
        Tool(
            "read_content",
            "读取原文 / 字幕 / 评论",
            "读取一条采集内容的原文（text）、字幕（subtitles，B站 / YouTube）或热门评论（comments）。",
            {
                "type": "object",
                "properties": {
                    "content_id": {"type": "integer"},
                    "part": {"type": "string", "enum": ["text", "subtitles", "comments"], "default": "text"},
                },
                "required": ["content_id"],
            },
            _read_content,
        ),
        Tool(
            "platform_search",
            "平台搜索",
            "立刻在某个平台上搜索关键词（追踪词搜索），返回最新结果；不写入采集库。",
            {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": ["bilibili", "youtube", "github", "hn", "reddit"]},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8},
                },
                "required": ["platform", "query"],
            },
            _platform_search,
        ),
        Tool(
            "fetch_url",
            "抓取网页",
            "抓取一个公开网页的正文。",
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            _fetch_url,
        ),
        Tool(
            "add_favorite",
            "加入收藏",
            "把一条采集内容（content_id）或一个链接（url）收进灵感库。",
            {
                "type": "object",
                "properties": {
                    "content_id": {"type": "integer"},
                    "url": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
            _add_favorite,
            writes=True,
        ),
        Tool(
            "write_note",
            "记随笔",
            "写一条随笔（支持 #标签 和 [[双链]]）。",
            {"type": "object", "properties": {"body": {"type": "string"}}, "required": ["body"]},
            _write_note,
            writes=True,
        ),
        Tool(
            "read_bundle",
            "读取提示词包",
            "读取一个产出物（提示词包 / 讲解视频 / MV）的视频提示词包 Markdown：定稿脚本、分镜、风格、素材、交付要求。",
            {"type": "object", "properties": {"output_id": {"type": "integer"}}, "required": ["output_id"]},
            _read_bundle,
        ),
        Tool(
            "upload_output",
            "回传成片",
            "做完视频后把成片交回工作台：path 为本机视频文件的绝对路径，或 url 为可下载地址；可附 note 说明做法。",
            {
                "type": "object",
                "properties": {
                    "output_id": {"type": "integer"},
                    "path": {"type": "string", "description": "本机视频文件绝对路径（mp4 / mov / webm / mkv）"},
                    "url": {"type": "string", "description": "可下载的视频地址"},
                    "note": {"type": "string"},
                },
                "required": ["output_id"],
            },
            _upload_output,
            writes=True,
        ),
    )
}


def describe_tools(allowed: frozenset[str] | None = None) -> list[dict[str, Any]]:
    return [
        {"name": t.name, "title": t.title, "description": t.description, "inputSchema": t.schema, "writes": t.writes}
        for t in TOOLS.values()
        if allowed is None or t.name in allowed
    ]


async def call_tool(db: AsyncSession, name: str, args: dict[str, Any] | None, ctx: ToolContext | None = None) -> Any:
    ctx = ctx or ToolContext()
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"没有工具 {name}")
    if ctx.allowed is not None and name not in ctx.allowed:
        raise ToolDenied(f"令牌不允许调用 {name}")
    args = dict(args or {})
    async with trace_service.span(
        db,
        kind="tool",
        name=name,
        run_id=ctx.run_id,
        step_id=ctx.step_id,
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": name,
            "gen_ai.tool.call.arguments": {k: (str(v)[:200]) for k, v in args.items()},
        },
        payload={"tool": name, "arguments": args},
        via=ctx.via,
        token_id=ctx.token_id,
    ) as rec:
        result = await tool.handler(db, args, ctx)
        rec["result"] = result
        if isinstance(result, list):
            rec["summary"] = f"{len(result)} 条结果"
        return result


# ── 令牌 ──


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_token(
    db: AsyncSession,
    label: str,
    *,
    tools: list[str] | None = None,
    project_ids: list[int] | None = None,
    run_id: int | None = None,
    ttl_hours: float | None = 24,
) -> tuple[str, WorkbenchToken]:
    """发放限定范围的令牌；明文只在这里返回一次。"""
    bad = [t for t in tools or [] if t not in TOOLS]
    if bad:
        raise ToolError(f"未知工具：{', '.join(bad)}")
    raw = "cw_" + secrets.token_urlsafe(32)
    tok = WorkbenchToken(
        label=label[:100] or "外部 agent",
        token_hash=_hash(raw),
        tools=tools or None,
        project_ids=project_ids or None,
        run_id=run_id,
        expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours) if ttl_hours else None,
    )
    db.add(tok)
    await db.commit()
    return raw, tok


async def check_token(db: AsyncSession, raw: str | None) -> WorkbenchToken:
    if not raw:
        raise ToolDenied("缺少令牌")
    tok = (await db.execute(select(WorkbenchToken).where(WorkbenchToken.token_hash == _hash(raw)))).scalar_one_or_none()
    if tok is None or tok.revoked_at is not None:
        raise ToolDenied("令牌无效")
    exp = tok.expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp is not None and exp < datetime.now(UTC):
        raise ToolDenied("令牌已过期")
    tok.last_used_at = datetime.now(UTC)
    await db.commit()
    return tok


def token_context(tok: WorkbenchToken) -> ToolContext:
    return ToolContext(
        run_id=tok.run_id,
        via="mcp",
        token_id=tok.id,
        allowed=frozenset(tok.tools) if tok.tools else None,
        project_ids=frozenset(int(p) for p in tok.project_ids) if tok.project_ids else None,
    )


def token_view(tok: WorkbenchToken) -> dict[str, Any]:
    return {
        "id": tok.id,
        "label": tok.label,
        "tools": tok.tools,
        "project_ids": tok.project_ids,
        "run_id": tok.run_id,
        "expires_at": tok.expires_at,
        "revoked_at": tok.revoked_at,
        "last_used_at": tok.last_used_at,
        "created_at": tok.created_at,
    }


async def list_tokens(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (await db.execute(select(WorkbenchToken).order_by(WorkbenchToken.id.desc()).limit(100))).scalars()
    return [token_view(t) for t in rows]


async def revoke_token(db: AsyncSession, token_id: int) -> bool:
    tok = await db.get(WorkbenchToken, token_id)
    if tok is None:
        return False
    tok.revoked_at = datetime.now(UTC)
    await db.commit()
    return True


# ── MCP（Streamable HTTP，JSON 响应） ──

MCP_PROTOCOL = "2025-06-18"


async def handle_mcp(db: AsyncSession, raw_token: str | None, message: dict[str, Any]) -> dict[str, Any] | None:
    """处理一条 JSON-RPC 消息；通知（无 id）返回 None。"""
    mid = message.get("id")
    method = message.get("method")

    def ok(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code: int, msg: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}}

    try:
        tok = await check_token(db, raw_token)
    except ToolDenied as exc:
        return err(-32001, str(exc)) if mid is not None else None
    ctx = token_context(tok)
    if mid is None:  # notifications/initialized 等
        return None
    if method == "initialize":
        return ok(
            {
                "protocolVersion": MCP_PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "creative-workbench", "title": "创意工作台", "version": "0.3"},
                "instructions": "创意工作台的工作台工具：搜索灵感库与采集内容、读原文 / 字幕 / 评论、收藏、记随笔；read_bundle 读取视频提示词包，做完后用 upload_output 回传成片。",
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok(
            {
                "tools": [
                    {k: v for k, v in t.items() if k in ("name", "title", "description", "inputSchema")}
                    for t in describe_tools(ctx.allowed)
                ]
            }
        )
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            result = await call_tool(db, str(params.get("name") or ""), params.get("arguments") or {}, ctx)
        except ToolDenied as exc:
            return err(-32001, str(exc))
        except ToolError as exc:
            return ok({"content": [{"type": "text", "text": str(exc)}], "isError": True})
        import json

        text = json.dumps(result, ensure_ascii=False, default=str)
        return ok({"content": [{"type": "text", "text": text}], "structuredContent": {"result": result}})
    return err(-32601, f"不支持的方法 {method}")
