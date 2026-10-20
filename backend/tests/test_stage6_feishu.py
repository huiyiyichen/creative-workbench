"""阶段 6：飞书多维表格——设置、测试连接、记入飞书、阶段变化更新状态列、自动写入、失败进任务中心。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio

from app.core.exceptions import AppException, ValidationError
from app.models.content import ContentItem
from app.models.feishu import FeishuRecord
from app.models.metrics import ContentMetrics
from app.schemas.projects import ProjectCreate
from app.services import feishu_service as fs, project_service as ps, task_service

COLUMNS = [
    {"field_name": "标题", "type": 1},
    {"field_name": "链接", "type": 15},
    {"field_name": "平台", "type": 3},
    {"field_name": "发布时间", "type": 5},
    {"field_name": "原始指标", "type": 1},
    {"field_name": "结论与理由", "type": 1},
    {"field_name": "追踪词", "type": 4},
    {"field_name": "状态", "type": 3},
    {"field_name": "工作台链接", "type": 15},
]


class FakeFeishu:
    def __init__(self):
        self.records: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict | None]] = []
        self.deny = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        path = req.url.path
        self.calls.append((req.method, path, body))
        if path.endswith("/tenant_access_token/internal"):
            if body["app_secret"] != "secret-1":
                return httpx.Response(200, json={"code": 10014, "msg": "app secret invalid"})
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200})
        assert req.headers["authorization"] == "Bearer t-abc"
        if path.endswith("/wiki/v2/spaces/get_node"):
            return httpx.Response(
                200, json={"code": 0, "data": {"node": {"obj_type": "bitable", "obj_token": "bascnFromWiki"}}}
            )
        if path.endswith("/fields"):
            return httpx.Response(200, json={"code": 0, "data": {"items": COLUMNS, "has_more": False}})
        if self.deny:
            return httpx.Response(403, json={"code": 91403, "msg": "Forbidden"})
        if req.method == "POST" and path.endswith("/records"):
            rid = f"rec{len(self.records) + 1}"
            self.records[rid] = dict(body["fields"])
            return httpx.Response(
                200, json={"code": 0, "data": {"record": {"record_id": rid, "fields": body["fields"]}}}
            )
        if req.method == "PUT":
            rid = path.rsplit("/", 1)[-1]
            self.records[rid].update(body["fields"])
            return httpx.Response(200, json={"code": 0, "data": {"record": {"record_id": rid}}})
        return httpx.Response(404, json={"code": 404, "msg": "not found"})


@pytest_asyncio.fixture
async def feishu(test_session_factory, monkeypatch):
    fake = FakeFeishu()
    monkeypatch.setattr(fs, "TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setattr(fs, "SESSION_FACTORY", test_session_factory)
    fs._token_cache.clear()
    return fake


async def _configure(db, **kw):
    return await fs.save_settings(
        db,
        {
            "app_id": "cli_a1",
            "app_secret": "secret-1",
            "table_url": "https://acme.feishu.cn/base/bascnAPP123?table=tblXYZ&view=vew1",
            **kw,
        },
    )


async def _content(db):
    c = ContentItem(
        title="每天 601 美元的编码智能体",
        url="https://example.com/a",
        platform="hn",
        source_type="RSS",
        status="crawled",
        published_at=datetime(2026, 10, 18, 8, 0, tzinfo=UTC),
        verdict="worth",
        verdict_data={
            "label": "值得做",
            "reason": "多平台热议",
            "basis": {"relevance": {"keyword_hits": ["智能体", "Codex"]}},
        },
    )
    db.add(c)
    await db.flush()
    db.add(ContentMetrics(content_id=c.id, views=12000, likes=830, comments=95))
    await db.commit()
    return c


def test_parse_table_url():
    assert fs.parse_table_url("https://x.feishu.cn/base/bascnA?table=tbl1&view=v") == ("base", "bascnA", "tbl1")
    assert fs.parse_table_url("https://x.feishu.cn/wiki/wikcnB?table=tbl2") == ("wiki", "wikcnB", "tbl2")
    with pytest.raises(ValidationError):
        fs.parse_table_url("https://x.feishu.cn/base/bascnA")
    with pytest.raises(ValidationError):
        fs.parse_table_url("ftp://x")


@pytest.mark.asyncio
async def test_settings_test_and_record_content(feishu, test_session_factory):
    async with test_session_factory() as db:
        with pytest.raises(ValidationError):
            await fs.sync(db, "content", 1)
        view = await _configure(db, field_map={"topic": "专题"})
        assert view["configured"] and view["has_secret"] and "secret-1" not in json.dumps(view)
        assert view["app_token"] == "bascnAPP123" and view["table_id"] == "tblXYZ"

        t = await fs.test_connection(db)
        assert t["ok"] and [m["column"] for m in t["missing"]] == ["专题"]

        c = await _content(db)
        res = await fs.sync(db, "content", c.id)
        assert res["status"] == "synced" and res["record_id"] == "rec1" and res["skipped_columns"] == ["专题"]
        f = feishu.records["rec1"]
        assert f["标题"] == c.title and f["链接"] == {"link": c.url, "text": c.url}
        assert f["平台"] == "hn" and f["发布时间"] == int(c.published_at.timestamp() * 1000)
        assert f["原始指标"] == "播放 12000 · 赞 830 · 评论 95"
        assert f["结论与理由"] == "值得做：多平台热议" and f["追踪词"] == ["智能体", "Codex"]
        assert f["状态"] == "未开始" and f["工作台链接"]["link"].endswith(f"/items/{c.id}")

        # 再记一次是更新同一条
        res2 = await fs.sync(db, "content", c.id)
        assert res2["record_id"] == "rec1" and len(feishu.records) == 1
        assert [m for m, _p, _b in feishu.calls].count("PUT") == 1
        assert (await fs.get_record(db, "content", c.id))["status"] == "synced"


@pytest.mark.asyncio
async def test_project_status_updates_and_auto(feishu, test_session_factory):
    async with test_session_factory() as db:
        await _configure(db, auto_on_project=True)
        c = await _content(db)
        p = await ps.create_project(db, 1, ProjectCreate(theme="编码智能体", sources=[f"content:{c.id}"]))
        await fs.drain()
        rec = (await db.execute(FeishuRecord.__table__.select())).first()
        assert rec is not None and rec.trigger == "auto"
        f = feishu.records[rec.record_id]
        assert f["标题"] == "编码智能体" and f["状态"] == "未开始" and f["链接"]["link"] == c.url
        assert f["工作台链接"]["link"].endswith(f"/projects/{p['id']}")

        project = await ps.get_project(db, p["id"])
        project.spec = {**(project.spec or {}), "draft": {"title": "x", "body": "第一段。"}}
        await db.commit()
        await ps.finalize(db, p["id"])
        await fs.drain()
        assert feishu.records[rec.record_id]["状态"] == "创作中"
        put = [b for m, _p, b in feishu.calls if m == "PUT"][-1]
        assert list(put["fields"]) == ["状态"]  # 阶段变化只更新状态列

        from app.models.studio import StudioOutput

        o = StudioOutput(project_id=p["id"], kind="wechat", status="draft", content={})
        db.add(o)
        await db.commit()
        from app.schemas.projects import OutputPatch

        await ps.patch_output(db, o.id, OutputPatch(published_url="https://mp.weixin.qq.com/s/1"))
        await fs.drain()
        assert feishu.records[rec.record_id]["状态"] == "已产出"


@pytest.mark.asyncio
async def test_failure_task_center_retry_and_wiki(feishu, test_session_factory):
    async with test_session_factory() as db:
        await _configure(db, table_url="https://acme.feishu.cn/wiki/wikcnNODE?table=tblW")
        c = await _content(db)
        feishu.deny = True
        with pytest.raises(AppException) as err:
            await fs.sync(db, "content", c.id)
        assert "添加文档应用" in err.value.message
        assert (await fs.get_settings(db))["app_token"] == "bascnFromWiki"
        rows = (await task_service.list_tasks(db, types=["feishu"]))["items"]
        assert rows[0]["status"] == "failed" and rows[0]["can_retry"] and "添加文档应用" in rows[0]["hint"]
        assert rows[0]["title"] == c.title

        feishu.deny = False
        out = await task_service.retry(db, rows[0]["key"])
        assert out["status"] == "synced"
        assert (await task_service.list_tasks(db, types=["feishu"]))["items"][0]["status"] == "done"

        fs._token_cache.clear()
        await fs.save_settings(db, {"app_secret": "wrong"})
        with pytest.raises(AppException) as err:
            await fs.test_connection(db)
        assert "app secret invalid" in err.value.message


@pytest.mark.asyncio
async def test_auto_on_worth(feishu, test_session_factory):
    async with test_session_factory() as db:
        await _configure(db, auto_on_worth=True)
        c = await _content(db)
        await fs.on_verdicts(db, [c.id])
        await fs.drain()
        await fs.on_verdicts(db, [c.id])  # 已写过不重复
        await fs.drain()
        assert len(feishu.records) == 1


def test_api_base(monkeypatch):
    monkeypatch.delenv("CW_FEISHU_API_BASE", raising=False)
    assert fs.api_base({"table_url": "https://a.feishu.cn/base/x?table=t"}) == fs.API_BASE
    assert fs.api_base({"table_url": "https://a.larksuite.com/base/x?table=t"}) == fs.LARK_BASE
    monkeypatch.setenv("CW_FEISHU_API_BASE", "http://127.0.0.1:9/open-apis/")
    assert fs.api_base({}) == "http://127.0.0.1:9/open-apis"
