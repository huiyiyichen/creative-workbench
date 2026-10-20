"""项目复制（当模板用）与批量归档 / 删除。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.project import Project, ProjectSource
from app.schemas.projects import ProjectCreate
from app.services import project_service as ps


def _id(p):
    return p["id"] if isinstance(p, dict) else p.id


@pytest.mark.asyncio
async def test_duplicate_and_batch(test_session_factory):
    async with test_session_factory() as db:
        a = _id(await ps.create_project(db, 1, ProjectCreate(theme="原项目", mode="article")))
        db.add(ProjectSource(project_id=a, content_id=None, library_item_id=7, role="main", snapshot={"title": "来源"}))
        await db.commit()
        copy = await ps.duplicate_project(db, a, 1)
        cid = copy["id"] if "id" in copy else copy["project"]["id"]
        assert cid != a
        p = await db.get(Project, cid)
        assert p.title == "原项目（副本）" and p.version == 0 and p.finalized_version is None
        srcs = (await db.execute(select(ProjectSource).where(ProjectSource.project_id == cid))).scalars().all()
        assert [s.library_item_id for s in srcs] == [7]

        b = _id(await ps.create_project(db, 1, ProjectCreate(theme="另一个")))
        r = await ps.batch_projects(db, [a, b, 999], "archive")
        assert r == {"done": 2, "skipped": [], "missing": [999]}
        r = await ps.batch_projects(db, [cid], "delete")
        assert r["skipped"] == [cid]  # 没归档的不删
        r = await ps.batch_projects(db, [b], "delete")
        assert r["done"] == 1
        assert await db.get(Project, b) is None
        r = await ps.batch_projects(db, [a], "unarchive")
        assert (await db.get(Project, a)).archived_at is None
