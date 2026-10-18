"""托盘状态判断与通知去重（平台无关部分）。"""

from app.desktop.tray import compute_status, new_notifications


def test_down_when_backend_not_ready():
    assert compute_status(backend_ok=False, paused=None, health_rows=None).state == "down"


def test_paused_wins_over_alerts():
    rows = [{"name": "A", "state": "error", "enabled": True}]
    assert compute_status(backend_ok=True, paused=True, health_rows=rows).state == "paused"


def test_alert_lists_problem_sources():
    rows = [
        {"name": "A", "state": "error", "enabled": True},
        {"name": "B", "state": "ok", "enabled": True},
        {"name": "C", "state": "paused", "enabled": True},
        {"name": "D", "state": "error", "enabled": False},
    ]
    status = compute_status(backend_ok=True, paused=False, health_rows=rows)
    assert status.state == "alert"
    assert status.alerts == ["A", "C"]


def test_running_when_all_ok():
    rows = [{"name": "A", "state": "ok", "enabled": True}, {"name": "B", "state": "empty", "enabled": True}]
    assert compute_status(backend_ok=True, paused=False, health_rows=rows).state == "running"


def test_new_notifications_only_newer_ids():
    items = [{"id": 3}, {"id": 5}, {"id": 4}]
    fresh, newest = new_notifications(items, 3)
    assert [n["id"] for n in fresh] == [4, 5]
    assert newest == 5
    assert new_notifications([], 7) == ([], 7)
