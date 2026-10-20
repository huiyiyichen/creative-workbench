"""飞书多维表格（改造方案 10.2）：把选题 / 项目单向写进飞书表格。

* 接入：飞书自建应用 App ID / App Secret（Secret 本地加密），表格链接解析出 app_token 与 table_id
  （`/base/<app_token>?table=<table_id>`；知识库里的表格 `/wiki/<node>?table=` 先换出 obj_token）。
* 字段映射：工作台的默认字段 → 飞书表格的列名；写入时按列的类型转换（链接、日期、数字、单选 / 多选、文本）。
  表格里没有的列跳过，并在结果里列出。
* 写入：条目详情 / 项目里「记入飞书」；可选自动写入（结论为「值得做」时、新建项目时）。保存 record_id，
  项目阶段变化时更新状态列（未开始 / 创作中 / 已产出）。单向，飞书里的修改不回写。
* 记录：`feishu_records` 一行一个对象 × 表格；失败进任务中心，可重试。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundError, ValidationError
from app.models.app_setting import AppSetting
from app.models.content import ContentItem
from app.models.feishu import FeishuRecord

logger = logging.getLogger(__name__)

SETTING_KEY = "feishu_bitable"
API_BASE = "https://open.feishu.cn/open-apis"
FIELDS: list[tuple[str, str]] = [
    ("title", "标题"),
    ("url", "链接"),
    ("platform", "平台"),
    ("published_at", "发布时间"),
    ("metrics", "原始指标"),
    ("verdict", "结论与理由"),
    ("keywords", "追踪词"),
    ("topic", "专题"),
    ("status", "状态"),
    ("workbench_url", "工作台链接"),
]
FIELD_LABELS = dict(FIELDS)
STATUS_NOT_STARTED, STATUS_CREATING, STATUS_DONE = "未开始", "创作中", "已产出"
# 飞书多维表格字段类型
T_TEXT, T_NUMBER, T_SELECT, T_MULTI, T_DATE, T_URL = 1, 2, 3, 4, 5, 15
SESSION_FACTORY = None  # 测试替换
_token_cache: dict[str, tuple[str, float]] = {}
_bg: set[asyncio.Task] = set()


class FeishuError(AppException):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message, status_code, {"code": "feishu_failed"})


# ── 设置 ──


async def _load(db: AsyncSession) -> dict[str, Any]:
    row = await db.get(AppSetting, SETTING_KEY)
    if row is None or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except ValueError:
        return {}


async def _store(db: AsyncSession, data: dict[str, Any]) -> None:
    row = await db.get(AppSetting, SETTING_KEY)
    if row is None:
        db.add(AppSetting(key=SETTING_KEY, value=json.dumps(data, ensure_ascii=False), description="飞书多维表格"))
    else:
        row.value = json.dumps(data, ensure_ascii=False)
    await db.commit()


def parse_table_url(url: str) -> tuple[str, str, str]:
    """返回 (kind, token, table_id)：kind 为 base（token 即 app_token）或 wiki（token 是知识库节点）。"""
    u = urlparse((url or "").strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValidationError("表格链接需以 http(s):// 开头")
    m = re.search(r"/(base|wiki)/([A-Za-z0-9]+)", u.path)
    table = (parse_qs(u.query).get("table") or [""])[0]
    if not m:
        raise ValidationError("没认出表格链接：应形如 https://xxx.feishu.cn/base/<app_token>?table=<table_id>")
    if not table:
        raise ValidationError("链接里没有 table 参数：请在表格里打开要写入的数据表后再复制链接")
    return m.group(1), m.group(2), table


def settings_view(data: dict[str, Any]) -> dict[str, Any]:
    mapping = {k: (data.get("field_map") or {}).get(k, label) for k, label in FIELDS}
    secret = data.get("app_secret_enc")
    return {
        "app_id": data.get("app_id") or "",
        "has_secret": bool(secret),
        "table_url": data.get("table_url") or "",
        "app_token": data.get("app_token"),
        "table_id": data.get("table_id"),
        "field_map": mapping,
        "fields": [{"key": k, "label": label} for k, label in FIELDS],
        "auto_on_worth": bool(data.get("auto_on_worth")),
        "auto_on_project": bool(data.get("auto_on_project")),
        "configured": configured(data),
    }


def configured(data: dict[str, Any]) -> bool:
    return bool(data.get("app_id") and data.get("app_secret_enc") and data.get("app_token") and data.get("table_id"))


async def get_settings(db: AsyncSession) -> dict[str, Any]:
    return settings_view(await _load(db))


async def save_settings(db: AsyncSession, values: dict[str, Any]) -> dict[str, Any]:
    from app.services.secret_store import encrypt_secret

    data = await _load(db)
    if values.get("app_id") is not None:
        data["app_id"] = values["app_id"].strip()
    if values.get("app_secret") is not None:
        data["app_secret_enc"] = encrypt_secret(values["app_secret"].strip()) if values["app_secret"].strip() else None
    if values.get("table_url") is not None:
        url = values["table_url"].strip()
        if url:
            kind, token, table = parse_table_url(url)
            data.update(table_url=url, table_id=table, link_kind=kind, link_token=token)
            data["app_token"] = token if kind == "base" else None  # 知识库链接在测试连接 / 首次写入时换出
        else:
            for k in ("table_url", "table_id", "app_token", "link_kind", "link_token"):
                data.pop(k, None)
    if values.get("field_map") is not None:
        fm = {k: str(v).strip()[:100] for k, v in values["field_map"].items() if k in FIELD_LABELS}
        data["field_map"] = fm
    for k in ("auto_on_worth", "auto_on_project"):
        if values.get(k) is not None:
            data[k] = bool(values[k])
    await _store(db, data)
    _token_cache.clear()
    return settings_view(data)


# ── 接口 ──


class Client:
    def __init__(self, app_id: str, app_secret: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.transport = transport

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=20, transport=self.transport)

    @staticmethod
    def _check(r: httpx.Response, what: str) -> dict[str, Any]:
        try:
            body = r.json()
        except ValueError as exc:
            raise FeishuError(f"{what}失败：HTTP {r.status_code}") from exc
        code = body.get("code")
        if r.status_code >= 400 or (code not in (0, None)):
            msg = body.get("msg") or body.get("message") or f"HTTP {r.status_code}"
            hint = ""
            if code in (99991663, 99991661, 99991668):
                hint = "（应用凭证无效或过期）"
            elif code in (91403, 1254302, 1254304):
                hint = "（应用没有这张表格的权限：在表格右上角「…→ 添加文档应用」里加上这个应用）"
            elif code in (1254045,):
                hint = "（列名不存在，检查字段映射）"
            raise FeishuError(f"{what}失败：{msg}{hint}（code {code}）")
        return body.get("data") or body

    async def token(self) -> str:
        cached = _token_cache.get(self.app_id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        async with self._http() as c:
            r = await c.post(
                f"{API_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
        body = self._check(r, "获取应用凭证")
        tok = body.get("tenant_access_token")
        if not tok:
            raise FeishuError("获取应用凭证失败：没有返回 tenant_access_token")
        _token_cache[self.app_id] = (tok, time.time() + float(body.get("expire") or 3600))
        return tok

    async def _req(self, method: str, path: str, what: str, **kw: Any) -> dict[str, Any]:
        tok = await self.token()
        async with self._http() as c:
            r = await c.request(method, f"{API_BASE}{path}", headers={"Authorization": f"Bearer {tok}"}, **kw)
        return self._check(r, what)

    async def wiki_obj_token(self, node_token: str) -> str:
        data = await self._req("GET", "/wiki/v2/spaces/get_node", "读取知识库节点", params={"token": node_token})
        node = data.get("node") or {}
        if node.get("obj_type") != "bitable" or not node.get("obj_token"):
            raise FeishuError("这个知识库节点不是多维表格")
        return node["obj_token"]

    async def fields(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page: str | None = None
        for _ in range(10):
            params: dict[str, Any] = {"page_size": 100}
            if page:
                params["page_token"] = page
            data = await self._req(
                "GET", f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields", "读取表格字段", params=params
            )
            out += [
                {"name": f.get("field_name"), "type": f.get("type"), "id": f.get("field_id")}
                for f in data.get("items") or []
            ]
            if not data.get("has_more"):
                break
            page = data.get("page_token")
        return out

    async def create(self, app_token: str, table_id: str, fields: dict[str, Any]) -> str:
        data = await self._req(
            "POST", f"/bitable/v1/apps/{app_token}/tables/{table_id}/records", "写入记录", json={"fields": fields}
        )
        rid = (data.get("record") or {}).get("record_id")
        if not rid:
            raise FeishuError("写入记录失败：没有返回 record_id")
        return rid

    async def update(self, app_token: str, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
        await self._req(
            "PUT",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            "更新记录",
            json={"fields": fields},
        )


TRANSPORT: httpx.AsyncBaseTransport | None = None  # 测试替换


async def _client(db: AsyncSession, data: dict[str, Any] | None = None) -> tuple[Client, dict[str, Any]]:
    from app.services.secret_store import decrypt_secret

    data = data if data is not None else await _load(db)
    if not (data.get("app_id") and data.get("app_secret_enc") and data.get("table_id")):
        raise ValidationError("先在「设置 · 飞书」填好 App ID、App Secret 和表格链接")
    client = Client(data["app_id"], decrypt_secret(data["app_secret_enc"]) or "", transport=TRANSPORT)
    if not data.get("app_token"):
        if data.get("link_kind") == "wiki" and data.get("link_token"):
            data["app_token"] = await client.wiki_obj_token(data["link_token"])
            await _store(db, data)
        else:
            raise ValidationError("表格链接无效")
    return client, data


async def test_connection(db: AsyncSession) -> dict[str, Any]:
    client, data = await _client(db)
    fields = await client.fields(data["app_token"], data["table_id"])
    names = {f["name"] for f in fields}
    mapping = settings_view(data)["field_map"]
    return {
        "ok": True,
        "fields": fields,
        "missing": [{"key": k, "column": col} for k, col in mapping.items() if col and col not in names],
    }


# ── 行数据 ──


def _iso(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _metrics_text(m: Any) -> str:
    if m is None:
        return ""
    parts = []
    for attr, label in (
        ("views", "播放"),
        ("likes", "赞"),
        ("comments", "评论"),
        ("shares", "转发"),
        ("favorites", "收藏"),
    ):
        v = getattr(m, attr, None)
        if v:
            parts.append(f"{label} {v}")
    return " · ".join(parts)


async def _app_url(db: AsyncSession) -> str:
    from app.services.obsidian_sync import get_settings as obsidian_settings

    try:
        url = (await obsidian_settings(db)).get("app_url") or ""
    except Exception:  # noqa: BLE001
        url = ""
    return (url or "http://localhost:3000").rstrip("/")


async def content_row(db: AsyncSession, content_id: int) -> dict[str, Any]:
    from app.models.metrics import ContentMetrics
    from app.models.topic import TopicGroup

    c = await db.get(ContentItem, content_id)
    if c is None:
        raise NotFoundError("内容", content_id)
    m = (
        await db.execute(
            select(ContentMetrics)
            .where(ContentMetrics.content_id == c.id)
            .order_by(ContentMetrics.snapshot_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    vd = c.verdict_data or {}
    verdict = ""
    if vd.get("label") or c.verdict:
        verdict = f"{vd.get('label') or c.verdict}：{vd.get('reason') or ''}".rstrip("：")
    keywords = ((vd.get("basis") or {}).get("relevance") or {}).get("keyword_hits") or []
    topic = await db.get(TopicGroup, c.topic_id) if c.topic_id else None
    return {
        "title": c.title,
        "url": c.url,
        "platform": c.platform or c.source_name or c.source_type or "",
        "published_at": _iso(c.published_at or c.crawled_at),
        "metrics": _metrics_text(m),
        "verdict": verdict,
        "keywords": [str(k) for k in keywords],
        "topic": getattr(topic, "title", None) or getattr(topic, "name", None) or "",
        "status": STATUS_NOT_STARTED,
        "workbench_url": f"{await _app_url(db)}/items/{c.id}",
    }


async def project_status(db: AsyncSession, project_id: int) -> str:
    from app.models.studio import StudioOutput, StudioProject

    p = await db.get(StudioProject, project_id)
    if p is None:
        raise NotFoundError("项目", project_id)
    done = (
        await db.execute(
            select(StudioOutput.id)
            .where(StudioOutput.project_id == project_id, StudioOutput.status.in_(("done", "exported", "published")))
            .limit(1)
        )
    ).first()
    if done:
        return STATUS_DONE
    if p.stage == "idea" and not p.finalized_version:
        return STATUS_NOT_STARTED
    return STATUS_CREATING


async def project_row(db: AsyncSession, project_id: int) -> dict[str, Any]:
    from app.models.studio import ProjectSource, StudioProject

    p = await db.get(StudioProject, project_id)
    if p is None:
        raise NotFoundError("项目", project_id)
    src = (
        await db.execute(
            select(ProjectSource)
            .where(ProjectSource.project_id == p.id, ProjectSource.content_id.is_not(None))
            .order_by(ProjectSource.role != "main", ProjectSource.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    row: dict[str, Any] = {
        "title": p.title,
        "url": "",
        "platform": "",
        "published_at": None,
        "metrics": "",
        "verdict": "",
        "keywords": [],
        "topic": "",
    }
    if src is not None:
        try:
            base = await content_row(db, src.content_id)
            row.update(
                {k: base[k] for k in ("url", "platform", "published_at", "metrics", "verdict", "keywords", "topic")}
            )
        except NotFoundError:
            pass
    row["status"] = await project_status(db, p.id)
    row["workbench_url"] = f"{await _app_url(db)}/projects/{p.id}"
    return row


def _value(ftype: int | None, v: Any) -> Any:
    if v in (None, "", []):
        return None
    if ftype == T_URL:
        return {"link": str(v), "text": str(v)[:200]}
    if ftype == T_DATE:
        if isinstance(v, datetime):
            return int(v.timestamp() * 1000)
        return None
    if ftype == T_NUMBER:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    if ftype == T_MULTI:
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]
    if isinstance(v, datetime):
        return v.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
    if isinstance(v, list):
        return "、".join(str(x) for x in v)
    return str(v)


def build_fields(
    row: dict[str, Any], mapping: dict[str, str], columns: list[dict[str, Any]], *, only: set[str] | None = None
) -> tuple[dict[str, Any], list[str]]:
    types = {c["name"]: c.get("type") for c in columns}
    out: dict[str, Any] = {}
    skipped: list[str] = []
    for key, col in mapping.items():
        if only is not None and key not in only:
            continue
        if not col:
            continue
        if col not in types:
            skipped.append(col)
            continue
        val = _value(types[col], row.get(key))
        if val is not None:
            out[col] = val
    return out, skipped


# ── 同步 ──


def record_view(r: FeishuRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "object_type": r.object_type,
        "object_id": r.object_id,
        "record_id": r.record_id,
        "status": r.status,
        "error": r.error,
        "trigger": r.trigger,
        "synced_at": r.synced_at.isoformat() if r.synced_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


async def get_record(db: AsyncSession, object_type: str, object_id: int) -> dict[str, Any] | None:
    data = await _load(db)
    stmt = select(FeishuRecord).where(FeishuRecord.object_type == object_type, FeishuRecord.object_id == object_id)
    if data.get("table_id"):
        stmt = stmt.where(FeishuRecord.table_id == data["table_id"])
    r = (await db.execute(stmt.order_by(FeishuRecord.id.desc()).limit(1))).scalar_one_or_none()
    return record_view(r) if r else None


async def sync(
    db: AsyncSession, object_type: str, object_id: int, *, trigger: str = "manual", only_status: bool = False
) -> dict[str, Any]:
    """写入或更新一条记录。失败时记为 failed（进任务中心）并抛出。"""
    if object_type not in ("content", "project"):
        raise ValidationError("只能记入内容或项目")
    client, data = await _client(db)
    rec = (
        await db.execute(
            select(FeishuRecord).where(
                FeishuRecord.object_type == object_type,
                FeishuRecord.object_id == object_id,
                FeishuRecord.table_id == data["table_id"],
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        if only_status:
            return {"skipped": True}
        rec = FeishuRecord(
            object_type=object_type,
            object_id=object_id,
            app_token=data["app_token"],
            table_id=data["table_id"],
            trigger=trigger,
        )
        db.add(rec)
        await db.flush()
    rec.status = "pending"
    rec.trigger = trigger if rec.record_id is None else rec.trigger
    await db.commit()
    try:
        row = await (content_row(db, object_id) if object_type == "content" else project_row(db, object_id))
        columns = await client.fields(data["app_token"], data["table_id"])
        mapping = settings_view(data)["field_map"]
        only = {"status"} if (only_status and rec.record_id) else None
        fields, skipped = build_fields(row, mapping, columns, only=only)
        if not fields:
            raise ValidationError("表格里没有映射到的列，检查字段映射")
        if rec.record_id:
            await client.update(data["app_token"], data["table_id"], rec.record_id, fields)
        else:
            rec.record_id = await client.create(data["app_token"], data["table_id"], fields)
        rec.status = "synced"
        rec.error = None
        rec.synced_at = datetime.now(UTC)
        await db.commit()
        return {**record_view(rec), "skipped_columns": skipped, "fields": list(fields)}
    except AppException as exc:
        rec.status = "failed"
        rec.error = exc.message[:500]
        await db.commit()
        raise
    except httpx.HTTPError as exc:
        rec.status = "failed"
        rec.error = f"连接飞书失败：{exc.__class__.__name__}"
        await db.commit()
        raise FeishuError(rec.error) from exc


async def retry(db: AsyncSession, record_id: int) -> dict[str, Any]:
    rec = await db.get(FeishuRecord, record_id)
    if rec is None:
        raise NotFoundError("飞书记录", record_id)
    return await sync(db, rec.object_type, rec.object_id, trigger=rec.trigger)


# ── 自动写入 / 状态更新（后台，不阻塞调用方）──


def _session() -> AsyncSession:
    if SESSION_FACTORY is not None:
        return SESSION_FACTORY()
    from app.core.database import async_session

    return async_session()


async def _bg_sync(object_type: str, object_id: int, trigger: str, only_status: bool) -> None:
    try:
        async with _session() as db:
            await sync(db, object_type, object_id, trigger=trigger, only_status=only_status)
    except Exception as exc:  # noqa: BLE001
        logger.info("feishu %s %s %s skipped: %s", trigger, object_type, object_id, exc)


def _spawn(coro) -> None:
    try:
        t = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        return
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def drain() -> None:
    """测试用：等后台写入结束。"""
    while _bg:
        await asyncio.gather(*list(_bg), return_exceptions=True)


async def on_project_created(db: AsyncSession, project_id: int) -> None:
    data = await _load(db)
    if configured(data) and data.get("auto_on_project"):
        _spawn(_bg_sync("project", project_id, "auto", False))


async def on_project_stage(db: AsyncSession, project_id: int) -> None:
    """项目阶段变化：已记入的项目更新状态列。"""
    data = await _load(db)
    if not configured(data):
        return
    exists = (
        await db.execute(
            select(FeishuRecord.id).where(
                FeishuRecord.object_type == "project",
                FeishuRecord.object_id == project_id,
                FeishuRecord.record_id.is_not(None),
            )
        )
    ).first()
    if exists:
        _spawn(_bg_sync("project", project_id, "stage", True))


async def on_verdicts(db: AsyncSession, content_ids: list[int]) -> None:
    """结论变成「值得做」时自动写入（已写过的不重复）。"""
    data = await _load(db)
    if not (configured(data) and data.get("auto_on_worth") and content_ids):
        return
    done = set(
        (
            await db.execute(
                select(FeishuRecord.object_id).where(
                    FeishuRecord.object_type == "content", FeishuRecord.object_id.in_(content_ids)
                )
            )
        ).scalars()
    )
    for cid in content_ids:
        if cid not in done:
            _spawn(_bg_sync("content", cid, "auto", False))


async def failed_records(db: AsyncSession, since: datetime, limit: int) -> list[FeishuRecord]:
    return list(
        (
            await db.execute(
                select(FeishuRecord)
                .where(FeishuRecord.updated_at >= since)
                .order_by(FeishuRecord.id.desc())
                .limit(limit)
            )
        ).scalars()
    )
