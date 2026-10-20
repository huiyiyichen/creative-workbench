"""从备份还原（先停掉后端！）：

    cd backend
    uv run python scripts/restore_backup.py data/backups/cw-backup-20261021-033000.tar.gz [--files] [--yes]

- 数据库：pg_dump 格式用 pg_restore --clean 还原到 DATABASE_URL；JSONL 格式按表顺序清空后导回；
- --files：同时把素材目录覆盖回 data/（原目录先改名为 *.before-restore 留底）。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _decode(v):
    if isinstance(v, dict) and "__b64" in v:
        return base64.b64decode(v["__b64"])
    return v


async def restore_jsonl(db_dir: Path) -> None:
    from sqlalchemy import DateTime, delete, insert

    import app.models  # noqa: F401
    from app.core.database import Base, engine

    order = json.loads((db_dir / "_order.json").read_text(encoding="utf-8"))
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    async with engine.begin() as conn:
        for name in reversed(order):
            if name in tables:
                await conn.execute(delete(tables[name]))
        for name in order:
            table = tables.get(name)
            path = db_dir / f"{name}.jsonl"
            if table is None or not path.exists():
                continue
            batch = []
            for line in path.open(encoding="utf-8"):
                row = {k: _decode(v) for k, v in json.loads(line).items() if k in table.c}
                for col in table.c:
                    if isinstance(col.type, DateTime) and isinstance(row.get(col.name), str):
                        row[col.name] = datetime.fromisoformat(row[col.name])
                batch.append(row)
                if len(batch) >= 500:
                    await conn.execute(insert(table), batch)
                    batch = []
            if batch:
                await conn.execute(insert(table), batch)
    print(f"已导回 {len(order)} 张表")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--files", action="store_true", help="同时还原素材目录")
    ap.add_argument("--yes", action="store_true", help="不再确认")
    args = ap.parse_args()
    from app.core.config import settings
    from app.services.backup_service import DATA_ROOT, _pg_url

    if not args.yes and input("会覆盖当前数据库（和素材目录）。确定还原？输入 yes：").strip() != "yes":
        print("已取消")
        return
    with tempfile.TemporaryDirectory() as tmpd, tarfile.open(args.archive, "r:gz") as tar:
        tar.extractall(tmpd, filter="data")
        tmp = Path(tmpd)
        manifest = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        if manifest["db_format"] == "pg_dump":
            pg = _pg_url(settings.DATABASE_URL)
            subprocess.run(
                ["pg_restore", "--clean", "--if-exists", "--no-owner", "-d", pg, str(tmp / "db.dump")], check=True
            )
            print("数据库已用 pg_restore 还原")
        else:
            asyncio.run(restore_jsonl(tmp / "db"))
        if args.files:
            for d in manifest.get("files") or []:
                target = DATA_ROOT / d
                if target.exists():
                    target.rename(target.with_name(f"{d}.before-restore"))
                shutil.copytree(tmp / "files" / d, target)
                print(f"已还原 data/{d}")


if __name__ == "__main__":
    main()
