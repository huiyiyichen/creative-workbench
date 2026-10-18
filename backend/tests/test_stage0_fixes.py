"""阶段 0 的缺陷修复（改造方案第 13 节）。"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.source import SourceType
from app.models.user import User, UserRole
from app.services.auth_service import get_local_user
from app.services.metrics_persistence import _get_process_metrics
from app.services.report_catchup import _month_key_for_ref, _week_key_for_ref, missing_periods
from app.services.scrapers.recognizer import normalize_creator_source, recognize_source_type


def test_process_metrics_use_psutil_not_resource():
    import app.services.metrics_persistence as mp

    assert not hasattr(mp, "resource")
    metrics = _get_process_metrics()
    assert metrics["process_rss_mb"] is None or metrics["process_rss_mb"] > 0


def test_douyin_account_route_is_recognized_as_subscription():
    route = "douyin/user/MS4wLjABAAAAabc-123"
    source_type, url, config = recognize_source_type(route)
    assert source_type == SourceType.RSSHub
    assert url == route
    assert config["platform"] == "douyin"


def test_misclassified_douyin_source_is_normalized_back():
    class Row:
        url = "douyin/user/MS4wLjABAAAAabc-123"
        keyword = None

    payload = normalize_creator_source({}, Row())
    assert payload["source_type"] == SourceType.RSSHub
    assert payload["platform"] == "douyin"


def test_douyin_hot_page_still_is_hot_list():
    source_type, _, _ = recognize_source_type("https://www.douyin.com/hot")
    assert source_type == SourceType.DOUYIN_HOT


@pytest.mark.asyncio
async def test_local_user_is_promoted_to_admin(db):
    db.add(User(email="old@example.com", display_name="旧用户", plan="free", role="user", is_active=False))
    await db.commit()

    user = await get_local_user(db)

    assert user.role == UserRole.ADMIN.value
    assert user.is_active is True
    assert len((await db.execute(select(User))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_local_user_is_created_once(db):
    first = await get_local_user(db)
    second = await get_local_user(db)
    assert first.id == second.id
    assert first.role == UserRole.ADMIN.value


def test_report_catchup_periods():
    today = date(2026, 10, 18)  # 周日
    days, week_refs, month_refs = missing_periods(today)
    assert days[0] == date(2026, 10, 17) and days[-1] == date(2026, 10, 11)
    assert len(week_refs) == 4 and len(month_refs) == 2
    # 参考日 10-12（周一）对应上一周 W41
    assert _week_key_for_ref(date(2026, 10, 12)) == "2026-W41"
    assert _month_key_for_ref(date(2026, 10, 1)) == "2026-09"
    assert _month_key_for_ref(date(2026, 1, 1)) == "2025-12"


@pytest.mark.asyncio
async def test_report_catchup_only_generates_missing(db, monkeypatch):
    from app.models.weekly_digest import WeeklyDigest
    from app.services import daily_report, monthly_digest, report_catchup, weekly_digest

    db.add(WeeklyDigest(week_key="2026-W41", week_label="x", week_start="2026-10-05", week_end="2026-10-11"))
    await db.commit()
    calls: dict[str, list] = {"daily": [], "weekly": [], "monthly": []}

    async def fake_daily(db, *, target_date, edition):
        calls["daily"].append(target_date)

    async def fake_weekly(db, reference_date):
        calls["weekly"].append(reference_date)

    async def fake_monthly(db, reference_date):
        calls["monthly"].append(reference_date)

    monkeypatch.setattr(daily_report, "generate_daily_report", fake_daily)
    monkeypatch.setattr(weekly_digest, "generate_weekly_digest", fake_weekly)
    monkeypatch.setattr(monthly_digest, "generate_monthly_digest", fake_monthly)

    done = await report_catchup.catch_up_reports(db, today=date(2026, 10, 18))

    assert len(calls["daily"]) == 7
    assert "2026-W41" not in done["weekly"] and len(done["weekly"]) == 3
    assert done["monthly"] == ["2026-08", "2026-09"]
