"""一键备份：列表、开始、下载、删除。还原用命令行 scripts/restore_backup.py。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.services import backup_service as svc

router = APIRouter(prefix="/backups", tags=["backups"], dependencies=[Depends(get_current_user)])


class BackupBody(BaseModel):
    include_files: bool = True


@router.get("")
async def list_backups():
    return {"items": svc.list_backups(), "keep": svc.KEEP, "root": str(svc.BACKUP_ROOT)}


@router.post("")
async def create_backup(body: BackupBody):
    return svc.start_backup(include_files=body.include_files)


@router.get("/{name}/download")
async def download_backup(name: str):
    path = svc.archive_file(name)
    return FileResponse(path, media_type="application/gzip", filename=path.name)


@router.delete("/{name}")
async def delete_backup(name: str):
    svc.delete_backup(name)
    return {"ok": True}
