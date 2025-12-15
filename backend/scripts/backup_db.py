#!/usr/bin/env python
"""
Create a timestamped backup of the SQLite database and optional assets directory.

Usage:
    python scripts/backup_db.py --db ./app.db --out ./backups
    python scripts/backup_db.py restore --db ./app.db --backup ./backups/app-20250101T120000Z.db
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup(db_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    dest = out_dir / f"{db_path.stem}-{ts}{db_path.suffix}"
    shutil.copy2(db_path, dest)
    return dest


def restore(backup_path: Path, db_path: Path) -> None:
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup/restore SQLite DB.")
    subparsers = parser.add_subparsers(dest="command")

    parser.add_argument("--db", default="./app.db", help="path to SQLite DB")
    parser.add_argument("--out", default="./backups", help="backup directory")

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--db", default="./app.db", help="destination DB path")
    restore_parser.add_argument("--backup", required=True, help="backup file to restore")

    args = parser.parse_args()
    if args.command == "restore":
        restore(Path(args.backup), Path(args.db))
        print(f"Restored {args.backup} -> {args.db}")
        return

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"DB not found: {db_path}")
    dest = backup(db_path, Path(args.out))
    print(f"Backup written to {dest}")


if __name__ == "__main__":
    main()
