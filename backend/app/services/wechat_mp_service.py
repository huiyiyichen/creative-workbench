"""公众号草稿箱直推（review 2026-10-20b）：把「公众号版」产出物推到公众号后台的草稿箱。

流程：取 access_token（AppID + AppSecret，后台需把服务器出口 IP 加进白名单）→ 正文里的图片逐张上传
（media/uploadimg，换成微信图床链接）→ 封面上传为永久素材（material/add_material?type=image）→ draft/add。
封面优先用项目素材里角色为「封面」的图，没有就按标题生成一张信号图封面。
推送成功记在产出物 settings.wechat_draft，状态改为「已导出」。
"""

from __future__ import annotations

import io
import json
import logging
import math
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ValidationError
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

SETTING_KEY = "wechat_mp"
API_BASE = "https://api.weixin.qq.com"
_token_cache: dict[str, tuple[str, float]] = {}

ERR_HINT = {
    40001: "AppSecret 不对，或者 token 已失效",
    40013: "AppID 不对",
    40125: "AppSecret 不对",
    40164: "服务器出口 IP 不在公众号后台的白名单里（设置与开发 → 基本配置 → IP 白名单）",
    41001: "缺少 access_token",
    45009: "接口调用次数超过当日上限",
    48001: "这个公众号没有草稿箱接口权限（需要已认证的服务号或订阅号）",
    40007: "素材 media_id 无效",
}


class WechatError(AppException):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message, status_code=status_code)


def api_base(data: dict[str, Any]) -> str:
    import os

    return (os.environ.get("CW_WECHAT_API_BASE") or data.get("api_base") or API_BASE).rstrip("/")


# ── 设置 ──


async def _load(db: AsyncSession) -> dict[str, Any]:
    row = await db.get(AppSetting, SETTING_KEY)
    if row is None or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except ValueError:
        return {}


async def _store(db: AsyncSession, data: dict[str, Any]) -> None:
    row = await db.get(AppSetting, SETTING_KEY)
    if row is None:
        db.add(AppSetting(key=SETTING_KEY, value=json.dumps(data, ensure_ascii=False), description="公众号草稿箱"))
    else:
        row.value = json.dumps(data, ensure_ascii=False)
    await db.commit()


def settings_view(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "app_id": data.get("app_id") or "",
        "has_secret": bool(data.get("app_secret_enc")),
        "author": data.get("author") or "",
        "source_url": data.get("source_url") or "",
        "open_comment": bool(data.get("open_comment")),
        "configured": bool(data.get("app_id") and data.get("app_secret_enc")),
        "last_test": data.get("last_test"),
    }


async def get_settings(db: AsyncSession) -> dict[str, Any]:
    return settings_view(await _load(db))


async def save_settings(db: AsyncSession, values: dict[str, Any]) -> dict[str, Any]:
    from app.services.secret_store import encrypt_secret

    data = await _load(db)
    if values.get("app_id") is not None:
        data["app_id"] = values["app_id"].strip()
    if values.get("app_secret") is not None:
        secret = values["app_secret"].strip()
        data["app_secret_enc"] = encrypt_secret(secret) if secret else None
    for k in ("author", "source_url"):
        if values.get(k) is not None:
            data[k] = str(values[k]).strip()[:200]
    if values.get("open_comment") is not None:
        data["open_comment"] = bool(values["open_comment"])
    await _store(db, data)
    _token_cache.clear()
    return settings_view(data)


async def _credentials(db: AsyncSession) -> tuple[dict[str, Any], str, str]:
    from app.services.secret_store import decrypt_secret

    data = await _load(db)
    if not (data.get("app_id") and data.get("app_secret_enc")):
        raise ValidationError("先在「设置 · 公众号」填 AppID 和 AppSecret")
    return data, data["app_id"], decrypt_secret(data["app_secret_enc"])


# ── 接口 ──


class Client:
    def __init__(
        self, app_id: str, app_secret: str, *, base: str = API_BASE, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base = base
        self.transport = transport

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), transport=self.transport)

    @staticmethod
    def _check(r: httpx.Response, what: str) -> dict[str, Any]:
        try:
            body = r.json()
        except ValueError as exc:
            raise WechatError(f"{what}失败：HTTP {r.status_code}") from exc
        code = body.get("errcode")
        if r.status_code >= 400 or code not in (0, None):
            msg = body.get("errmsg") or f"HTTP {r.status_code}"
            hint = ERR_HINT.get(code)
            raise WechatError(f"{what}失败：{hint or msg}（errcode {code}）")
        return body

    async def token(self) -> str:
        cached = _token_cache.get(self.app_id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        async with self._http() as c:
            r = await c.post(
                f"{self.base}/cgi-bin/stable_token",
                json={"grant_type": "client_credential", "appid": self.app_id, "secret": self.app_secret},
            )
        body = self._check(r, "获取 access_token")
        tok = body["access_token"]
        _token_cache[self.app_id] = (tok, time.time() + int(body.get("expires_in") or 7200))
        return tok

    async def upload_content_image(self, data: bytes, filename: str) -> str:
        tok = await self.token()
        async with self._http() as c:
            r = await c.post(
                f"{self.base}/cgi-bin/media/uploadimg", params={"access_token": tok}, files={"media": (filename, data)}
            )
        return self._check(r, "上传正文图片")["url"]

    async def upload_cover(self, data: bytes, filename: str) -> str:
        tok = await self.token()
        async with self._http() as c:
            r = await c.post(
                f"{self.base}/cgi-bin/material/add_material",
                params={"access_token": tok, "type": "image"},
                files={"media": (filename, data)},
            )
        return self._check(r, "上传封面")["media_id"]

    async def add_draft(self, article: dict[str, Any]) -> str:
        tok = await self.token()
        async with self._http() as c:
            r = await c.post(
                f"{self.base}/cgi-bin/draft/add",
                params={"access_token": tok},
                content=json.dumps({"articles": [article]}, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"},
            )
        return self._check(r, "写入草稿箱")["media_id"]


async def client_for(db: AsyncSession, *, transport: httpx.AsyncBaseTransport | None = None) -> Client:
    data, app_id, secret = await _credentials(db)
    return Client(app_id, secret, base=api_base(data), transport=transport)


async def test_connection(db: AsyncSession, *, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    client = await client_for(db, transport=transport)
    _token_cache.pop(client.app_id, None)
    await client.token()
    data = await _load(db)
    data["last_test"] = datetime.now(UTC).isoformat()
    await _store(db, data)
    return {"ok": True, "message": "连接成功：拿到了 access_token"}


# ── 封面与正文 ──

_IMG_RE = re.compile(r"""<img\b[^>]*?\bsrc=["']([^"']+)["'][^>]*>""", re.I)


def make_cover(title: str) -> bytes:
    """没有封面图时按标题生成一张 900×383 的信号图封面（深底、网格、两条迹线、标题）。"""
    from PIL import Image, ImageDraw, ImageFont

    w, h = 900, 383
    img = Image.new("RGB", (w, h), (15, 18, 22))
    d = ImageDraw.Draw(img)
    for y in range(0, h, 48):
        d.line([(0, y), (w, y)], fill=(30, 35, 42))
    for x in range(0, w, 48):
        d.line([(x, 0), (x, h)], fill=(24, 28, 34))
    seed = sum(ord(ch) for ch in title or "·")
    for amp, col, phase in ((26, (90, 70, 110), 1.3), (44, (232, 92, 214), 0.0)):
        pts = [
            (x, h * 0.62 + math.sin(x / 38 + seed % 7 + phase) * amp * (0.6 + 0.4 * math.sin(x / 97 + seed)))
            for x in range(0, w + 1, 6)
        ]
        d.line(pts, fill=col, width=3)
    font = None
    for path in ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"):
        try:
            font = ImageFont.truetype(path, 44)
            break
        except OSError:
            continue
    text = (title or "").strip()[:22]
    if font and text:
        d.text((48, 60), text, font=font, fill=(240, 242, 236))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


async def _cover_bytes(db: AsyncSession, project_id: int, title: str) -> tuple[bytes, str]:
    from app.models.library import LibraryItem
    from app.models.project import ProjectAsset
    from app.services.library_files import abs_path

    asset = (
        (
            await db.execute(
                select(ProjectAsset)
                .where(ProjectAsset.project_id == project_id, ProjectAsset.role == "cover")
                .order_by(ProjectAsset.added_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if asset:
        item = await db.get(LibraryItem, asset.library_item_id)
        if item and item.file_path:
            try:
                p = abs_path(item.file_path)
                return p.read_bytes(), p.name
            except Exception:  # noqa: BLE001 — 读不到就用生成的封面
                logger.info("cover asset unreadable for project %s", project_id)
    return make_cover(title), "cover.jpg"


async def _image_bytes(src: str) -> tuple[bytes, str] | None:
    """正文图片：本地 /api/v1/library/... 或 http(s) 链接；data: 和读不到的跳过。"""
    from urllib.parse import urlparse

    if src.startswith("data:"):
        return None
    m = re.search(r"/library/items/(\d+)/file", src)
    if m:
        from app.core.database import async_session
        from app.models.library import LibraryItem
        from app.services.library_files import abs_path

        async with async_session() as db:
            item = await db.get(LibraryItem, int(m.group(1)))
        if item and item.file_path:
            p = abs_path(item.file_path)
            return p.read_bytes(), p.name
        return None
    if urlparse(src).scheme in ("http", "https"):
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=True) as c:
            r = await c.get(src)
            if r.status_code < 400:
                return r.content, (urlparse(src).path.rsplit("/", 1)[-1] or "image.jpg")[:60]
    return None


async def rewrite_images(html: str, upload) -> tuple[str, int, list[str]]:
    """把正文里的图片换成微信图床链接；返回 (新正文, 上传张数, 跳过的 src)。"""
    done: dict[str, str] = {}
    skipped: list[str] = []
    for src in dict.fromkeys(_IMG_RE.findall(html)):
        if "mmbiz.qpic.cn" in src:
            continue
        try:
            got = await _image_bytes(src)
            if got is None:
                skipped.append(src)
                continue
            done[src] = await upload(*got)
        except WechatError:
            raise
        except Exception:  # noqa: BLE001 — 单张图失败不阻断推送，记下来告诉用户
            skipped.append(src)
    for old, new in done.items():
        html = html.replace(old, new)
    return html, len(done), skipped


def _digest(content: dict[str, Any]) -> str:
    text = content.get("summary") or re.sub(r"<[^>]+>", "", str(content.get("body") or ""))
    return re.sub(r"\s+", " ", text).strip()[:110]


async def push_draft(
    db: AsyncSession, output_id: int, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    from app.services import project_service as ps

    output = await ps.get_output(db, output_id)
    if output.kind != "wechat":
        raise ValidationError("只有「公众号版」能推到草稿箱")
    content = output.content or {}
    title = str(content.get("title") or output.title or "").strip()
    body = str(content.get("body") or "").strip()
    if not title or not body:
        raise ValidationError("标题和正文都不能为空")
    data = await _load(db)
    client = await client_for(db, transport=transport)
    body, uploaded, skipped = await rewrite_images(body, client.upload_content_image)
    cover, name = await _cover_bytes(db, output.project_id, title)
    thumb = await client.upload_cover(cover, name)
    article = {
        "title": title[:64],
        "author": (data.get("author") or "")[:16],
        "digest": _digest(content),
        "content": body,
        "content_source_url": data.get("source_url") or "",
        "thumb_media_id": thumb,
        "need_open_comment": 1 if data.get("open_comment") else 0,
        "only_fans_can_comment": 0,
    }
    media_id = await client.add_draft(article)
    record = {
        "media_id": media_id,
        "pushed_at": datetime.now(UTC).isoformat(),
        "images": uploaded,
        "skipped": skipped[:10],
    }
    output.settings = {**(output.settings or {}), "wechat_draft": record}
    if output.status in ("draft", "done"):
        output.status = "exported"
    await db.commit()
    return record
