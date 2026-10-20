"""托盘程序：显示运行 / 暂停 / 有异常，菜单打开工作台、记一笔、暂停采集、退出；
轮询站内通知并转成 Windows 系统通知。

运行：``pythonw -m app.desktop.tray --api http://127.0.0.1:8102 --ui http://127.0.0.1:3000``
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("creative_workbench.tray")

POLL_SECONDS = 30
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STATE_FILE = DATA_DIR / "tray-state.json"
RUNTIME_FILE = DATA_DIR / "runtime.json"

# 托盘图标颜色（与界面 token 一致）
COLOR_OK = (108, 207, 104)  # --gr
COLOR_PAUSED = (227, 204, 75)  # --yl
COLOR_ALERT = (255, 97, 89)  # --rd
COLOR_DOWN = (94, 103, 116)  # --faint


@dataclass
class TrayStatus:
    state: str  # running / paused / alert / down
    tooltip: str
    alerts: list[str] = field(default_factory=list)


def compute_status(
    *,
    backend_ok: bool,
    paused: bool | None,
    health_rows: list[dict[str, Any]] | None,
) -> TrayStatus:
    """把后端状态归成托盘的四种状态。"""
    if not backend_ok:
        return TrayStatus("down", "创意工作台：后台未运行")
    if paused:
        return TrayStatus("paused", "创意工作台：采集已暂停")
    problems = [
        row
        for row in (health_rows or [])
        if row.get("enabled", True) and row.get("state") in {"paused", "error", "stale"}
    ]
    if problems:
        names = [str(r.get("name")) for r in problems[:3]]
        more = f" 等 {len(problems)} 个" if len(problems) > 3 else ""
        return TrayStatus("alert", f"创意工作台：{'、'.join(names)}{more}需要处理", alerts=names)
    return TrayStatus("running", "创意工作台：采集运行中")


def new_notifications(items: list[dict[str, Any]], last_seen_id: int) -> tuple[list[dict[str, Any]], int]:
    """挑出比上次见过的更新的通知（按 id 升序），返回新的 last_seen_id。"""
    fresh = sorted((n for n in items if int(n.get("id", 0)) > last_seen_id), key=lambda n: int(n["id"]))
    newest = max([last_seen_id, *[int(n["id"]) for n in fresh]])
    return fresh, newest


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.debug("tray state not saved", exc_info=True)


def read_runtime() -> dict[str, Any]:
    """start-local.ps1 写入的端口信息。"""
    try:
        return json.loads(RUNTIME_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


class Backend:
    def __init__(self, api: str):
        self.api = api.rstrip("/")
        self.client = httpx.Client(timeout=8, trust_env=False)

    def ready(self) -> bool:
        try:
            return self.client.get(f"{self.api}/health/ready").status_code == 200
        except httpx.HTTPError:
            return False

    def get(self, path: str) -> Any:
        resp = self.client.get(f"{self.api}{path}")
        resp.raise_for_status()
        return resp.json()

    def set_paused(self, paused: bool) -> None:
        self.client.put(f"{self.api}/api/v1/collection/pause", json={"paused": paused}).raise_for_status()

    def snapshot(self) -> tuple[TrayStatus, list[dict[str, Any]]]:
        if not self.ready():
            return compute_status(backend_ok=False, paused=None, health_rows=None), []
        try:
            paused = bool(self.get("/api/v1/collection/pause").get("paused"))
            rows = self.get("/api/v1/collection/health").get("sources", [])
            notes = self.get("/api/v1/notifications?unread=true&limit=20").get("notifications", [])
        except (httpx.HTTPError, ValueError):
            logger.debug("tray poll failed", exc_info=True)
            return compute_status(backend_ok=True, paused=False, health_rows=None), []
        return compute_status(backend_ok=True, paused=paused, health_rows=rows), notes


def _icon_image(color: tuple[int, int, int]):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), outline=(51, 59, 72, 255), width=4)
    draw.ellipse((20, 20, 44, 44), fill=(*color, 255))
    return img


_COLORS = {"running": COLOR_OK, "paused": COLOR_PAUSED, "alert": COLOR_ALERT, "down": COLOR_DOWN}


def _toast(title: str, message: str, url: str | None = None) -> None:
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster("创意工作台")
        toast = Toast([title, message])
        if url:
            toast.on_activated = lambda _args: webbrowser.open(url)
        toaster.show_toast(toast)
    except Exception:
        logger.debug("toast failed", exc_info=True)


def run(api: str, ui: str) -> None:  # pragma: no cover - 需要 Windows 桌面
    import pystray

    backend = Backend(api)
    state = load_state()
    stop = threading.Event()
    current = {"status": compute_status(backend_ok=False, paused=None, health_rows=None)}

    def open_ui(*_args):
        webbrowser.open(ui)

    def open_capture(*_args):
        webbrowser.open(f"{ui}/inbox?capture=1")

    def toggle_pause(icon, _item):
        try:
            backend.set_paused(current["status"].state != "paused")
        except httpx.HTTPError:
            _toast("创意工作台", "后台未响应，暂停 / 恢复没有生效")
        refresh(icon)

    def quit_tray(icon, _item):
        stop.set()
        icon.stop()

    def refresh(icon):
        status, notes = backend.snapshot()
        current["status"] = status
        icon.icon = _icon_image(_COLORS[status.state])
        icon.title = status.tooltip
        last = int(state.get("last_notification_id", 0))
        fresh, newest = new_notifications(notes, last)
        if last == 0:
            fresh = []  # 首次启动不补发历史通知
        for note in fresh[-5:]:
            _toast(note.get("title") or "创意工作台", note.get("message") or "", f"{ui}/sources")
        if newest != last:
            state["last_notification_id"] = newest
            save_state(state)
        icon.update_menu()

    menu = pystray.Menu(
        pystray.MenuItem("打开工作台", open_ui, default=True),
        pystray.MenuItem("记一笔", open_capture),
        pystray.MenuItem(
            lambda _i: "恢复采集" if current["status"].state == "paused" else "暂停采集",
            toggle_pause,
            enabled=lambda _i: current["status"].state != "down",
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出托盘", quit_tray),
    )
    icon = pystray.Icon("creative-workbench", _icon_image(COLOR_DOWN), "创意工作台", menu)

    def loop(icon):
        icon.visible = True
        while not stop.is_set():
            try:
                refresh(icon)
            except Exception:
                logger.exception("tray refresh failed")
            stop.wait(POLL_SECONDS)

    icon.run(setup=loop)


def _single_instance() -> bool:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        return True
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\CreativeWorkbenchTray")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - 入口
    runtime = read_runtime()
    parser = argparse.ArgumentParser(description="创意工作台托盘")
    parser.add_argument(
        "--api", default=runtime.get("api") or os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8102")
    )
    parser.add_argument("--ui", default=runtime.get("ui") or "http://127.0.0.1:3000")
    args = parser.parse_args(argv)
    from logging.handlers import RotatingFileHandler

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            RotatingFileHandler(DATA_DIR / "tray.log", maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8")
        ],
    )
    if not _single_instance():
        return 0
    time.sleep(1)
    run(args.api, args.ui)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
