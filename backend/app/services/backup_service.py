"""一键备份（review 2026-10-20b）：数据库 + 素材目录打成一个 tar.gz，放在 data/backups/。

- 数据库：本机有 pg_dump 时用它导出（custom 格式，pg_restore 可还原）；没有时逐表导出 JSONL（还原脚本按表顺序导回）；
- 文件：灵感库、收藏媒体、生成结果、项目媒体、运行追踪；封面缓存、模型、浏览器配置不备份（可重新生成）；
- 每个备份旁边有一个同名 .json 状态文件（running / done / failed、大小、耗时）；
- 默认保留最近 10 份；每周日 03:30 自动备份一次。
还原见 scripts/restore_backup.py（命令行，需先停掉后端）。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

DATA_ROOT = (Path(__file__).resolve().parents[2] / "data").resolve()
BACKUP_ROOT = DATA_ROOT / "backups"
FILE_DIRS = ("library", "favorites", "generations", "studio", "traces")
KEEP = 10
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
_NAME_RE = re.compile(r"^cw-backup-\d{8}-\d{6}$")
_running: set[str] = set()
_tasks: set[asyncio.Task] = set()


def _status_path(name: str) -> Path:
    return BACKUP_ROOT / f"{name}.json"


def _archive_path(name: str) -> Path:
    return BACKUP_ROOT / f"{name}.tar.gz"


def _write_status(name: str, data: dict[str, Any]) -> None:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = _status_path(name).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_status_path(name))


def _check_name(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise ValidationError("备份名不对")
    return name


def list_backups() -> list[dict[str, Any]]:
    if not BACKUP_ROOT.exists():
        return []
    out = []
    for p in sorted(BACKUP_ROOT.glob("cw-backup-*.json"), reverse=True):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = p.name.removesuffix(".json")
        if st.get("status") == "running" and name not in _running:
            st["status"] = "failed"
            st["error"] = st.get("error") or "备份中途中断（后端重启了）"
        out.append({"name": name, **st})
    return out


def archive_file(name: str) -> Path:
    p = _archive_path(_check_name(name))
    if not p.exists():
        raise NotFoundError("备份文件不存在")
    return p


def delete_backup(name: str) -> None:
    _check_name(name)
    if name in _running:
        raise ValidationError("这份备份还在进行中")
    for p in (_archive_path(name), _status_path(name)):
        p.unlink(missing_ok=True)


def prune(keep: int = KEEP) -> int:
    done = [b for b in list_backups() if b.get("status") == "done"]
    removed = 0
    for b in done[keep:]:
        delete_backup(b["name"])
        removed += 1
    return removed


# ── 数据库导出 ──


def _pg_url(url: str) -> str | None:
    if not url.startswith("postgresql"):
        return None
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _pg_dump(url: str, dest: Path) -> bool:
    exe = shutil.which("pg_dump")
    pg = _pg_url(url)
    if not exe or not pg:
        return False
    r = subprocess.run(
        [exe, "--format=custom", "--no-owner", "--no-privileges", "-f", str(dest), pg],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if r.returncode != 0:
        logger.warning("pg_dump failed, falling back to JSONL: %s", r.stderr[-500:])
        dest.unlink(missing_ok=True)
        return False
    return True


def _jsonable(v: Any) -> Any:
    if isinstance(v, bytes | bytearray | memoryview):
        return {"__b64": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


async def _jsonl_dump(dest: Path) -> dict[str, int]:
    from sqlalchemy import select

    import app.models  # noqa: F401 — 注册全部表
    from app.core.database import Base, async_session

    dest.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    order = []
    async with async_session() as db:
        for table in Base.metadata.sorted_tables:
            n = 0
            with (dest / f"{table.name}.jsonl").open("w", encoding="utf-8") as f:
                result = await db.stream(select(table))
                async for row in result:
                    f.write(json.dumps({k: _jsonable(v) for k, v in row._mapping.items()}, ensure_ascii=False) + "\n")
                    n += 1
            counts[table.name] = n
            order.append(table.name)
    (dest / "_order.json").write_text(json.dumps(order), encoding="utf-8")
    return counts


# ── 主流程 ──


def new_name(now: datetime | None = None) -> str:
    now = (now or datetime.now(UTC)).astimezone(LOCAL_TZ)
    return now.strftime("cw-backup-%Y%m%d-%H%M%S")


async def run_backup(name: str, *, include_files: bool = True, database_url: str | None = None) -> dict[str, Any]:
    from app.core.config import settings

    started = time.monotonic()
    status: dict[str, Any] = {
        "status": "running",
        "created_at": datetime.now(UTC).isoformat(),
        "include_files": include_files,
    }
    _running.add(name)
    _write_status(name, status)
    try:
        with tempfile.TemporaryDirectory(prefix="cw-backup-") as tmpd:
            tmp = Path(tmpd)
            url = database_url if database_url is not None else settings.DATABASE_URL
            if await asyncio.to_thread(_pg_dump, url, tmp / "db.dump"):
                db_format, tables = "pg_dump", None
            else:
                db_format, tables = "jsonl", await _jsonl_dump(tmp / "db")
            dirs = [d for d in FILE_DIRS if include_files and (DATA_ROOT / d).is_dir()]
            manifest = {
                "app": "creative-workbench",
                "version": 1,
                "created_at": status["created_at"],
                "db_format": db_format,
                "tables": tables,
                "files": dirs,
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            def pack() -> None:
                BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
                part = _archive_path(name).with_suffix(".part")
                with tarfile.open(part, "w:gz") as tar:
                    tar.add(tmp / "manifest.json", arcname="manifest.json")
                    if db_format == "pg_dump":
                        tar.add(tmp / "db.dump", arcname="db.dump")
                    else:
                        tar.add(tmp / "db", arcname="db")
                    for d in dirs:
                        tar.add(DATA_ROOT / d, arcname=f"files/{d}")
                os.replace(part, _archive_path(name))

            await asyncio.to_thread(pack)
        status.update(
            status="done",
            db_format=db_format,
            files=dirs,
            size=_archive_path(name).stat().st_size,
            seconds=round(time.monotonic() - started, 1),
        )
    except Exception as exc:
        logger.exception("backup %s failed", name)
        _archive_path(name).with_suffix(".part").unlink(missing_ok=True)
        status.update(status="failed", error=str(exc)[:300])
    finally:
        _running.discard(name)
        _write_status(name, status)
    if status["status"] == "done":
        prune()
    return {"name": name, **status}


def start_backup(*, include_files: bool = True) -> dict[str, Any]:
    """后台开始一份备份，立刻返回名字；进度看 list_backups。"""
    if _running:
        raise ValidationError("已经有一份备份在进行中")
    name = new_name()
    _write_status(
        name, {"status": "running", "created_at": datetime.now(UTC).isoformat(), "include_files": include_files}
    )
    _running.add(name)
    task = asyncio.get_running_loop().create_task(run_backup(name, include_files=include_files), name=f"backup:{name}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"name": name, "status": "running"}
