"""阶段 5：提示词包与外部 agent 回传成片。"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.core.exceptions import AppException
from app.models.studio import StudioOutput
from app.schemas.projects import ProjectCreate
from app.services import delivery_service, studio_service, works_service
from app.services import project_service as ps
from app.services import workbench_tools as wt


@pytest.fixture
def media(tmp_path, monkeypatch):
    from app.services import trace_payloads

    monkeypatch.setattr(trace_payloads, "TRACE_ROOT", tmp_path / "traces")
    root = tmp_path / "studio"
    root.mkdir()
    monkeypatch.setattr(studio_service, "MEDIA_ROOT", root)
    return root


async def _bundle_output(db, theme="提示词包"):
    p = await ps.create_project(db, 1, ProjectCreate(theme=theme))
    project = await ps.get_project(db, p["id"])
    project.spec = {**(project.spec or {}), "draft": {"title": theme, "body": "第一段。\n\n第二段。"}}
    await db.commit()
    await ps.finalize(db, p["id"])
    o = StudioOutput(project_id=p["id"], kind="prompt_bundle", title="视频提示词包", status="exported", based_on_version=2)
    db.add(o)
    await db.commit()
    return p["id"], o.id


@pytest.mark.asyncio
async def test_mcp_read_bundle_and_upload_scoped(test_session_factory, media, tmp_path):
    async with test_session_factory() as db:
        pid, oid = await _bundle_output(db)
        _pid2, other = await _bundle_output(db, "别的项目")
        raw, _tok = await wt.issue_token(db, "Codex", project_ids=[pid])
        call = lambda name, args, i=1: wt.handle_mcp(  # noqa: E731
            db, raw, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
        )
        listed = await wt.handle_mcp(db, raw, {"jsonrpc": "2.0", "id": 0, "method": "tools/list"})
        names = {t["name"] for t in listed["result"]["tools"]}
        assert {"read_bundle", "upload_output"} <= names

        res = await call("read_bundle", {"output_id": oid})
        assert res["result"]["structuredContent"]["result"]["output_id"] == oid
        assert "提示词包" in res["result"]["structuredContent"]["result"]["title"]

        denied = await call("read_bundle", {"output_id": other})
        assert denied["error"]["code"] == -32001

        video = tmp_path / "final.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 2048)
        bad = await call("upload_output", {"output_id": oid, "path": "final.mp4"})
        assert bad["result"]["isError"]
        txt = tmp_path / "a.txt"
        txt.write_text("x")
        assert (await call("upload_output", {"output_id": oid, "path": str(txt)}))["result"]["isError"]
        ok = await call("upload_output", {"output_id": oid, "path": str(video), "note": "Remotion 渲染"})
        out = ok["result"]["structuredContent"]["result"]
        assert out["size"] == video.stat().st_size and video.exists()  # 本机文件是复制，不动原文件

        view = await ps.output_view(db, oid)
        assert view["status"] == "done"
        d = view["content"]["deliveries"][-1]
        assert d["source"] == "agent" and d["note"] == "Remotion 渲染" and d["file_name"] == "final.mp4"
        art = next(a for a in view["artifacts"] if a["id"] == out["artifact_id"])
        assert art["preview_path"] and art["download_path"]
        assert (media / f"deliveries/{pid}/{out['artifact_id']}.mp4").is_file()
        # 作品库里能预览和下载
        works = await works_service.list_works(db, project_id=pid)
        item = works["groups"][0]["items"][0]
        assert item["preview_path"] == art["preview_path"]

        with pytest.raises(AppException):
            await delivery_service.attach(db, oid, tmp_path / "missing.mp4", filename="missing.mp4")


@pytest.mark.asyncio
async def test_upload_endpoint(test_session_factory, media):
    from app.api.v1 import projects as projects_api

    async with test_session_factory() as db:
        _pid, oid = await _bundle_output(db)

    app = FastAPI()
    app.include_router(projects_api.router)

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[projects_api.get_db] = override_get_db
    from app.core.exceptions import AppException as _E

    @app.exception_handler(_E)
    async def _h(_req, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/outputs/{oid}/deliveries", files={"file": ("cut.mov", b"x" * 1000, "video/quicktime")}, data={"note": "手动上传"})
        assert r.status_code == 200, r.text
        assert r.json()["delivery"]["source"] == "upload"
        r = await client.post(f"/outputs/{oid}/deliveries", files={"file": ("x.exe", b"x", "application/octet-stream")})
        assert r.status_code == 422
    incoming = media / "deliveries" / "_incoming"
    assert not any(incoming.iterdir())
