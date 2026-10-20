"""一键备份：打包数据库（JSONL 兜底）与素材目录、状态文件、保留份数、删除。"""

from __future__ import annotations

import json
import tarfile

import pytest

from app.core.exceptions import ValidationError
from app.models.library import Note
from app.services import backup_service as bk


@pytest.fixture
def roots(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "library" / "a").mkdir(parents=True)
    (data / "library" / "a" / "x.txt").write_text("素材")
    (data / "media").mkdir()
    monkeypatch.setattr(bk, "DATA_ROOT", data)
    monkeypatch.setattr(bk, "BACKUP_ROOT", data / "backups")
    return data


@pytest.mark.asyncio
async def test_backup_jsonl_roundtrip(roots, test_session_factory, monkeypatch):
    from app.core import database

    async with test_session_factory() as db:
        db.add(Note(body="备份里的随笔"))
        await db.commit()
    monkeypatch.setattr(database, "async_session", test_session_factory)

    name = bk.new_name()
    res = await bk.run_backup(name, database_url="")  # 非 PostgreSQL → JSONL
    assert res["status"] == "done" and res["db_format"] == "jsonl" and res["files"] == ["library"]
    items = bk.list_backups()
    assert items[0]["name"] == name and items[0]["size"] > 0
    with tarfile.open(bk.archive_file(name)) as tar:
        names = tar.getnames()
        assert "manifest.json" in names and "files/library/a/x.txt" in names
        assert not any(n.startswith("files/media") for n in names)
        notes = tar.extractfile("db/notes.jsonl").read().decode()
        assert "备份里的随笔" in notes
        order = json.loads(tar.extractfile("db/_order.json").read())
        assert "notes" in order

    with pytest.raises(ValidationError):
        bk.archive_file("../../etc/passwd")
    bk.delete_backup(name)
    assert bk.list_backups() == []


def test_prune_and_interrupted(roots):
    for i in range(12):
        n = f"cw-backup-20261021-0000{i:02d}"
        bk._write_status(n, {"status": "done", "created_at": "x"})
        bk._archive_path(n).write_bytes(b"x")
    bk._write_status("cw-backup-20261021-235959", {"status": "running"})
    assert bk.prune(keep=10) == 2
    items = bk.list_backups()
    assert items[0]["status"] == "failed" and "中断" in items[0]["error"]
    assert len([b for b in items if b["status"] == "done"]) == 10


def test_pg_url():
    assert bk._pg_url("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert bk._pg_url("sqlite+aiosqlite:///x") is None
