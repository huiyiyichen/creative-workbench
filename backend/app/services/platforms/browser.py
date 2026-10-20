"""浏览器采集统一管理（改造方案 3.2）：抖音、小红书。

* 每个平台一个独立的浏览器配置目录 ``data/browser/<platform>``（保存各自登录态），本机 Edge。
* 全局并发 1；按平台限频（两次打开页面之间至少间隔 ``MIN_INTERVAL`` 秒）。
* 读页面自身的接口响应（``capture``），不自己签名请求。
* 遇到登录页 / 验证码时抛 :class:`PlatformError`，信息里带「登录失效」「验证码」字样，由同步记录归类、自动处理（3.9）。
* 登录：``open_login`` 打开有界面的窗口让你在本机登录，关窗后登录态留在配置目录里。

测试里把 ``BROWSER`` 换成假实现即可，不需要 Playwright。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import PlatformError

logger = logging.getLogger(__name__)

PROFILE_ROOT = (Path(__file__).resolve().parents[3] / "data" / "browser").resolve()
MIN_INTERVAL = {"douyin": 15.0, "xiaohongshu": 45.0}
LOGIN_URL = {"douyin": "https://www.douyin.com/", "xiaohongshu": "https://www.xiaohongshu.com/explore"}
# 登录墙 / 验证码的识别：页面地址或正文里的关键字
LOGIN_MARKS = {
    "douyin": ("passport.douyin.com", "登录后即可"),
    "xiaohongshu": ("/login", "登录后查看更多", "扫码登录"),
}
CAPTCHA_MARKS = ("captcha", "verify.snssdk", "验证码", "滑块", "安全验证", "website-login/captcha")


@dataclass
class Captured:
    """一次打开页面收到的接口响应：按匹配名分组的 JSON 正文。"""

    responses: dict[str, list[Any]] = field(default_factory=dict)
    final_url: str = ""
    page_state: Any = None  # 页面里的初始状态（例如小红书 window.__INITIAL_STATE__）

    def first(self, name: str) -> Any:
        items = self.responses.get(name) or []
        return items[0] if items else None


def check_wall(platform: str, url: str, text: str) -> None:
    low = (url or "").lower()
    if any(m in low for m in CAPTCHA_MARKS) or any(m in (text or "") for m in CAPTCHA_MARKS if not m.isascii()):
        raise PlatformError(f"{platform} 出现验证码，请在「信源 · 浏览器登录」里打开窗口手动通过")
    for m in LOGIN_MARKS.get(platform, ()):
        if (m.startswith(("/", "passport")) and m in low) or (not m.isascii() and m in (text or "")):
            raise PlatformError(f"{platform} 登录失效，请在「信源 · 浏览器登录」里重新登录")


class BrowserPool:
    """全局并发 1 + 按平台限频。真正打开浏览器的只有 ``_open``。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last: dict[str, float] = {}

    def profile_dir(self, platform: str) -> Path:
        return PROFILE_ROOT / platform

    def status(self, platform: str) -> dict[str, Any]:
        d = self.profile_dir(platform)
        state = d / "workbench_state.json"
        info: dict[str, Any] = {}
        if state.is_file():
            with contextlib.suppress(ValueError, OSError):
                info = json.loads(state.read_text(encoding="utf-8"))
        return {"platform": platform, "profile": d.exists(), **info}

    def _mark(self, platform: str, **values: Any) -> None:
        d = self.profile_dir(platform)
        d.mkdir(parents=True, exist_ok=True)
        cur = self.status(platform)
        cur.pop("platform", None)
        cur.pop("profile", None)
        (d / "workbench_state.json").write_text(json.dumps({**cur, **values}, ensure_ascii=False), encoding="utf-8")

    async def capture(
        self,
        platform: str,
        url: str,
        matchers: dict[str, str],
        *,
        need: tuple[str, ...] = (),
        wait_seconds: float = 25,
        scroll: int = 0,
        state_script: str | None = None,
    ) -> Captured:
        """打开 url，收集地址里含 matchers[name] 的接口响应；``need`` 里的都收到（或超时）就返回。"""
        async with self._lock:
            gap = MIN_INTERVAL.get(platform, 5.0) - (time.monotonic() - self._last.get(platform, 0.0))
            if gap > 0:
                await asyncio.sleep(gap)
            try:
                result = await self._open(
                    platform, url, matchers, need or tuple(matchers), wait_seconds, scroll, state_script
                )
            except PlatformError as exc:
                self._mark(platform, last_error=str(exc), last_error_at=time.time())
                raise
            finally:
                self._last[platform] = time.monotonic()
            self._mark(platform, last_ok_at=time.time(), last_error=None)
            return result

    async def _open(
        self,
        platform: str,
        url: str,
        matchers: dict[str, str],
        need: tuple[str, ...],
        wait_seconds: float,
        scroll: int,
        state_script: str | None,
    ) -> Captured:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - 依赖缺失
            raise PlatformError("没有安装 Playwright，无法用浏览器采集") from exc
        out = Captured()
        pending: set[asyncio.Task] = set()

        async def read(response) -> None:
            for name, part in matchers.items():
                if part in response.url and response.status == 200:
                    with contextlib.suppress(Exception):
                        out.responses.setdefault(name, []).append(await response.json())

        def on_response(response) -> None:
            t = asyncio.create_task(read(response))
            pending.add(t)
            t.add_done_callback(pending.discard)

        self.profile_dir(platform).mkdir(parents=True, exist_ok=True)
        async with async_playwright() as pw:
            try:
                ctx = await pw.chromium.launch_persistent_context(
                    str(self.profile_dir(platform)),
                    channel="msedge",
                    headless=True,
                    viewport={"width": 1440, "height": 1000},
                    locale="zh-CN",
                )
            except Exception as exc:  # noqa: BLE001
                raise PlatformError(f"无法启动本机 Edge：{exc}") from exc
            try:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                page.on("response", on_response)
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                deadline = time.monotonic() + wait_seconds
                scrolled = 0
                while time.monotonic() < deadline:
                    if all(out.responses.get(n) for n in need):
                        break
                    check_wall(platform, page.url, "")
                    if scrolled < scroll:
                        await page.mouse.wheel(0, 2400)
                        scrolled += 1
                    await asyncio.sleep(1)
                out.final_url = page.url
                text = ""
                with contextlib.suppress(Exception):
                    text = (await page.inner_text("body"))[:4000]
                if state_script:
                    with contextlib.suppress(Exception):
                        out.page_state = await page.evaluate(state_script)
                if not any(out.responses.values()) and out.page_state is None:
                    check_wall(platform, page.url, text)
                    raise PlatformError(f"{platform} 页面没有返回数据（接口可能变化或加载超时）")
            finally:
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                await ctx.close()
        return out

    async def open_login(self, platform: str, *, timeout: float = 600) -> dict[str, Any]:
        """有界面的窗口：你在本机完成登录后关窗，登录态留在这个平台的配置目录里。"""
        from playwright.async_api import async_playwright

        async with self._lock:
            self.profile_dir(platform).mkdir(parents=True, exist_ok=True)
            async with async_playwright() as pw:
                ctx = await pw.chromium.launch_persistent_context(
                    str(self.profile_dir(platform)), channel="msedge", headless=False, locale="zh-CN"
                )
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(LOGIN_URL[platform], wait_until="domcontentloaded")
                closed = asyncio.Event()
                ctx.on("close", lambda *_: closed.set())
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(closed.wait(), timeout)
                with contextlib.suppress(Exception):
                    await ctx.close()
            self._mark(platform, login_at=time.time(), last_error=None)
            return self.status(platform)


BROWSER = BrowserPool()
