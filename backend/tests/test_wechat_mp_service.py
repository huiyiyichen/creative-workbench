"""公众号草稿箱直推：token、正文图片换链、封面上传、写草稿；错误码给出可操作的提示。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.project import ProjectOutput
from app.schemas.projects import ProjectCreate
from app.services import project_service as ps, wechat_mp_service as wx


def _transport(calls: list, *, draft_error: int | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path.endswith("/stable_token"):
            body = json.loads(request.content)
            if body["secret"] != "s3cret":
                return httpx.Response(200, json={"errcode": 40125, "errmsg": "invalid appsecret"})
            return httpx.Response(200, json={"access_token": "TOKEN", "expires_in": 7200})
        assert request.url.params.get("access_token") == "TOKEN"
        if path.endswith("/media/uploadimg"):
            return httpx.Response(200, json={"url": "https://mmbiz.qpic.cn/x/1.jpg"})
        if path.endswith("/material/add_material"):
            return httpx.Response(200, json={"media_id": "THUMB", "url": "https://mmbiz.qpic.cn/c.jpg"})
        if path.endswith("/draft/add"):
            if draft_error:
                return httpx.Response(200, json={"errcode": draft_error, "errmsg": "api unauthorized"})
            art = json.loads(request.content)["articles"][0]
            assert art["thumb_media_id"] == "THUMB"
            assert "https://mmbiz.qpic.cn/x/1.jpg" in art["content"]
            assert art["author"] == "小陈"
            return httpx.Response(200, json={"media_id": "DRAFT1"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_make_cover_is_jpeg():
    data = wx.make_cover("这周 AI 圈发生了什么")
    assert data[:2] == b"\xff\xd8" and len(data) > 5000


@pytest.mark.asyncio
async def test_rewrite_images_skips_unreadable():
    async def upload(data, name):
        return "https://mmbiz.qpic.cn/new.jpg"

    html = '<p>a</p><img src="data:image/png;base64,xx"><img src="https://mmbiz.qpic.cn/old.jpg">'
    out, n, skipped = await wx.rewrite_images(html, upload)
    assert n == 0 and skipped == ["data:image/png;base64,xx"] and out == html


@pytest.mark.asyncio
async def test_push_draft(test_session_factory, monkeypatch):
    wx._token_cache.clear()

    async def fake_image(src):
        return (b"\xff\xd8img", "a.jpg")

    monkeypatch.setattr(wx, "_image_bytes", fake_image)
    calls: list = []
    async with test_session_factory() as db:
        with pytest.raises(NotFoundError):
            await wx.push_draft(db, 999999, transport=_transport(calls))
        proj = await ps.create_project(db, 1, ProjectCreate(theme="公众号测试"))
        pid = proj["id"] if isinstance(proj, dict) else proj.id
        out = ProjectOutput(
            project_id=pid,
            kind="wechat",
            title="公众号版",
            status="draft",
            content={"title": "标题", "body": '<p>正文</p><img src="https://ex.com/p.png">', "summary": "摘要"},
        )
        db.add(out)
        await db.commit()

        with pytest.raises(ValidationError):  # 没配置
            await wx.push_draft(db, out.id, transport=_transport(calls))

        await wx.save_settings(db, {"app_id": "wx123", "app_secret": "wrong", "author": "小陈"})
        with pytest.raises(wx.WechatError) as e:
            await wx.test_connection(db, transport=_transport(calls))
        assert "AppSecret" in e.value.message

        view = await wx.save_settings(db, {"app_secret": "s3cret"})
        assert view["configured"] and view["has_secret"] and "app_secret" not in view
        assert (await wx.test_connection(db, transport=_transport(calls)))["ok"]

        rec = await wx.push_draft(db, out.id, transport=_transport(calls))
        assert rec["media_id"] == "DRAFT1" and rec["images"] == 1
        await db.refresh(out)
        assert out.status == "exported" and out.settings["wechat_draft"]["media_id"] == "DRAFT1"

        with pytest.raises(wx.WechatError) as e:
            await wx.push_draft(db, out.id, transport=_transport(calls, draft_error=48001))
        assert "草稿箱接口权限" in e.value.message
