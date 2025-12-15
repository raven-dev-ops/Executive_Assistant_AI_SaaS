import json
import os
from pathlib import Path

import pytest

from scripts import backup_db, dr_drill


def test_backup_and_dr_drill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Prepare a tiny SQLite DB.
    db_path = tmp_path / "app.db"
    monkeypatch.chdir(tmp_path)
    # Create a minimal DB schema.
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE businesses (id TEXT);")
        conn.execute("INSERT INTO businesses (id) VALUES ('b1');")
        conn.commit()
    finally:
        conn.close()

    # Backup
    backup_dir = tmp_path / "backups"
    dest = backup_db.backup(db_path, backup_dir)
    assert dest.exists()

    # DR drill
    report = dr_drill.run_drill(dest, tmp_path / "restore.db")
    assert report["tables"]["businesses"] == 1
    # Save report
    out = tmp_path / "report.json"
    out.write_text(json.dumps(report))
    assert out.exists()
