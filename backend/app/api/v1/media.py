"""本地封面缓存（改造方案 3.4）：``GET /api/v1/media/{asset_id}?size=thumb|full``。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.content_observation import MediaAssetStatus
from app.repositories.media_asset_repo import MediaAssetRepository
from app.services.media_cache import resolve_asset_file

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{asset_id}")
async def get_media(
    asset_id: int,
    size: str = Query("thumb", pattern="^(thumb|full)$"),
    db: AsyncSession = Depends(get_db),
):
    repo = MediaAssetRepository(db)
    asset = await repo.get(asset_id)
    if asset is None or asset.status != MediaAssetStatus.READY.value:
        raise HTTPException(status_code=404, detail="封面未缓存")
    path = resolve_asset_file(asset, size)
    if path is None:
        raise HTTPException(status_code=404, detail="封面文件已清理")
    await repo.touch(asset_id, datetime.now(UTC))
    await db.commit()
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
