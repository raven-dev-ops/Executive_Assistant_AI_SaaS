#!/usr/bin/env python
"""
Lightweight DR drill helper for SQLite (dev/stub) to validate backups and capture RPO/RTO.

Steps:
- Copy the specified backup into a temp DB path.
- Run a simple smoke check (list businesses and appointments counts).
- Emit JSON with start/end timestamps, RPO, and basic health info.

Usage:
    python scripts/dr_drill.py --backup ./backups/app-20250101T120000Z.db --db ./backend/app.db --out ./dr_report.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return -1


def run_drill(backup_path: Path, temp_db: Path) -> dict:
    started_at = ts()
    start_epoch = time.time()
    temp_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, temp_db)
    conn = sqlite3.connect(temp_db)
    try:
        businesses = _count(conn, "businesses")
        appointments = _count(conn, "appointments")
        conversations = _count(conn, "conversations")
        users = _count(conn, "users")
    finally:
        conn.close()
    duration = time.time() - start_epoch
    return {
        "backup": str(backup_path),
        "restored_db": str(temp_db),
        "started_at": started_at,
        "completed_at": ts(),
        "duration_seconds": round(duration, 2),
        "tables": {
            "businesses": businesses,
            "appointments": appointments,
            "conversations": conversations,
            "users": users,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a DR drill against a SQLite backup.")
    parser.add_argument("--backup", required=True, help="Path to backup file")
    parser.add_argument("--db", default="./backend/app.db", help="Live DB path (for RPO calc)")
    parser.add_argument("--out", default="./dr_report.json", help="Path to write drill report JSON")
    parser.add_argument("--temp-db", default="./tmp/dr_restore.db", help="Temp restore DB path")
    args = parser.parse_args()

    backup_path = Path(args.backup)
    if not backup_path.exists():
        raise SystemExit(f"Backup not found: {backup_path}")

    # Estimate RPO: difference between now and backup mtime.
    try:
        mtime = backup_path.stat().st_mtime
        rpo_minutes = round((time.time() - mtime) / 60.0, 2)
    except Exception:
        rpo_minutes = None

    report = run_drill(backup_path, Path(args.temp_db))
    report["rpo_minutes"] = rpo_minutes

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
