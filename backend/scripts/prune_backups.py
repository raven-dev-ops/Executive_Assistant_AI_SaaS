#!/usr/bin/env python
"""
Prune old backups, keeping only the newest N files in a directory.

Usage:
    python scripts/prune_backups.py --dir ./backups --keep 10
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def prune(dir_path: Path, keep: int) -> list[Path]:
    files = sorted(
        [p for p in dir_path.iterdir() if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    for f in files[keep:]:
        try:
            f.unlink()
            removed.append(f)
        except Exception:
            pass
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune old backups (keep newest N).")
    parser.add_argument("--dir", default="./backups", help="backup directory")
    parser.add_argument("--keep", type=int, default=10, help="number of newest files to keep")
    args = parser.parse_args()

    target = Path(args.dir)
    if not target.exists():
        raise SystemExit(f"Backup directory not found: {target}")
    removed = prune(target, max(args.keep, 0))
    if removed:
        print(f"Removed {len(removed)} old backups.")
        for r in removed:
            print(f"- {r}")
    else:
        print("No backups pruned.")


if __name__ == "__main__":
    main()
