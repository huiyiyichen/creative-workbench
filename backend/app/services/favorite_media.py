from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path

from app.core.exceptions import ValidationError
from app.models.favorite import FavoriteTargetType

MEDIA_ROOT = (Path(__file__).resolve().parents[2] / "data" / "favorites").resolve()
MAX_BYTES = {
    FavoriteTargetType.IMAGE: 20 * 1024 * 1024,
    FavoriteTargetType.STYLE: 20 * 1024 * 1024,
    FavoriteTargetType.TEMPLATE: 20 * 1024 * 1024,
    FavoriteTargetType.AUDIO: 50 * 1024 * 1024,
    FavoriteTargetType.VIDEO: 200 * 1024 * 1024,
}
ALLOWED_EXTENSIONS = {
    FavoriteTargetType.IMAGE: {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"},
    FavoriteTargetType.STYLE: {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"},
    FavoriteTargetType.TEMPLATE: {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"},
    FavoriteTargetType.AUDIO: {".mp3", ".wav", ".m4a", ".ogg", ".flac"},
    FavoriteTargetType.VIDEO: {".mp4", ".webm", ".mov", ".m4v", ".avi"},
}
SAFE_NAME = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")


def store_media(*, user_id: int, target_type: FavoriteTargetType, filename: str, content: bytes) -> dict:
    if target_type not in MAX_BYTES:
        raise ValidationError("收藏类型不支持上传文件")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS[target_type]:
        raise ValidationError("文件类型与收藏类型不匹配")
    if len(content) > MAX_BYTES[target_type]:
        limit = MAX_BYTES[target_type] // (1024 * 1024)
        raise ValidationError(f"文件不得超过 {limit} MB")
    digest = hashlib.sha256(content).hexdigest()
    safe_name = SAFE_NAME.sub("-", Path(filename).name)[:120] or f"media{suffix}"
    relative = f"{user_id}/{digest[:16]}-{safe_name}"
    path = (MEDIA_ROOT / relative).resolve()
    if not path.is_relative_to(MEDIA_ROOT):
        raise ValidationError("文件名无效")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    return {
        "target_key": f"local:{digest}",
        "relative_path": relative,
        "mime_type": mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
        "sha256": digest,
        "name": safe_name,
    }


def safe_media_path(relative_path: str) -> Path:
    path = (MEDIA_ROOT / relative_path).resolve()
    if path == MEDIA_ROOT or not path.is_relative_to(MEDIA_ROOT):
        raise ValidationError("收藏媒体路径无效")
    return path
