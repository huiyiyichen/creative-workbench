"""阶段 5：作品库。"""

from __future__ import annotations

import pytest

from app.models.studio import StudioArtifact, StudioOutput
from app.schemas.projects import ProjectCreate
from app.services import project_service as ps
from app.services import works_service


@pytest.mark.asyncio
async def test_works_rules_groups_and_toggle(test_session_factory):
    async with test_session_factory() as db:
        a = await ps.create_project(db, 1, ProjectCreate(theme="编码智能体"))
        b = await ps.create_project(db, 1, ProjectCreate(theme="AI MV"))
        xhs = StudioOutput(
            project_id=a["id"], kind="xhs", title="小红书版", status="draft", content={"title": "601 美元", "body": "正文", "tags": ["AI"]}
        )
        wechat = StudioOutput(
            project_id=a["id"], kind="wechat", status="published", content={"title": "长文", "body": "<p>第一段</p><p>第二段</p>"}
        )
        video = StudioOutput(project_id=a["id"], kind="video", status="done", based_on_version=3)
        hidden = StudioOutput(project_id=b["id"], kind="zhihu", status="published", settings={"in_works": False})
        db.add_all([xhs, wechat, video, hidden])
        await db.flush()
        db.add(StudioArtifact(project_id=a["id"], version=3, kind="video", status="done", output_id=video.id, relative_path="x/a.mp4"))
        db.add(StudioArtifact(project_id=b["id"], version=1, kind="video", status="done", relative_path="old/b.mp4"))
        db.add(StudioArtifact(project_id=b["id"], version=2, kind="video", status="failed", relative_path="old/c.mp4"))
        await db.commit()

        data = await works_service.list_works(db)
        by = {g["project"]["id"]: g["items"] for g in data["groups"]}
        keys_a = {i["key"] for i in by[a["id"]]}
        assert keys_a == {f"output:{wechat.id}", f"output:{video.id}"}  # 草稿不自动收录
        w = next(i for i in by[a["id"]] if i["kind"] == "wechat")
        assert w["copy_text"] == "长文\n\n第一段 第二段" and w["excerpt"] == "第一段 第二段"
        v = next(i for i in by[a["id"]] if i["kind"] == "video")
        assert v["download_path"].endswith("/download") and v["based_on_version"] == 3
        assert [i["type"] for i in by[b["id"]]] == ["legacy"]  # 移出的不列，失败的旧成片不列

        await works_service.set_in_works(db, xhs.id, True)
        data = await works_service.list_works(db, project_id=a["id"])
        x = next(i for i in data["groups"][0]["items"] if i["kind"] == "xhs")
        assert x["manual"] and x["copy_text"] == "601 美元\n\n正文\n\n#AI"
        await works_service.set_in_works(db, wechat.id, False)
        assert f"output:{wechat.id}" not in {i["key"] for i in (await works_service.list_works(db, project_id=a["id"]))["groups"][0]["items"]}

        assert (await works_service.list_works(db, kind="xhs"))["total"] == 1
        assert (await works_service.list_works(db, q="AI MV"))["groups"][0]["project"]["id"] == b["id"]
        assert (await works_service.list_works(db, q="不存在"))["total"] == 0
