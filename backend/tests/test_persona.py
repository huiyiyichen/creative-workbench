"""创作人格：规则判定与按月统计。"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.core.exceptions import ValidationError
from app.models.library import LibraryItem
from app.models.project import Project, ProjectOutput
from app.services import persona_service as pz


def base(**kw):
    s = {
        "actions": 0,
        "projects": 0,
        "outputs": 0,
        "published": 0,
        "library": 0,
        "breakdowns": 0,
        "notes": 0,
        "revisions": 0,
        "days": 0,
        "streak": 0,
        "night_pct": 0,
        "platforms": 0,
        "videos": 0,
        "xhs": 0,
        "longform": 0,
    }
    s.update(kw)
    return s


def test_pick_rules():
    assert pz.pick(base(actions=2))[0] == "observer"
    assert pz.pick(base(actions=20, breakdowns=4))[0] == "hunter"
    assert pz.pick(base(actions=20, platforms=4))[0] == "multi"
    key, name, tagline = pz.pick(base(actions=30, night_pct=70))
    assert key == "night" and "70%" in tagline and name == "深夜写字人"
    assert pz.longest_streak({date(2026, 10, d) for d in (1, 2, 3, 5, 6)}) == 3


def test_month_range_beijing():
    start, end = pz.month_range("2026-10")
    assert start == datetime(2026, 9, 30, 16, tzinfo=UTC) and end == datetime(2026, 10, 31, 16, tzinfo=UTC)
    with pytest.raises(ValidationError):
        pz.month_range("2026/10")


@pytest.mark.asyncio
async def test_persona_counts(db):
    t = datetime(2026, 10, 5, 15, 30, tzinfo=UTC)  # 北京时间 23:30
    p = Project(
        owner_id=1, title="项目一", spec={}, source_snapshot={}, version=0, draft_token="x", stage="idea", created_at=t
    )
    db.add(p)
    await db.flush()
    for k in ("xhs", "douyin", "bilibili"):
        db.add(ProjectOutput(project_id=p.id, kind=k, title=k, status="draft", content={}, settings={}, created_at=t))
    db.add(LibraryItem(kind="link", title="爆款", url="https://e/1", import_method="breakdown", created_at=t))
    db.add(LibraryItem(kind="link", title="旧", url="https://e/2", created_at=datetime(2026, 9, 1, tzinfo=UTC)))
    await db.commit()
    r = await pz.persona(db, "2026-10")
    s = r["stats"]
    assert s["projects"] == 1 and s["outputs"] == 3 and s["library"] == 1 and s["breakdowns"] == 1
    assert s["platforms"] == 3 and s["night_pct"] == 100 and r["peak_hour"] == 23
    assert r["archetype"]["key"] in {"multi", "hunter", "night"} and r["titles"] == ["项目一"]
