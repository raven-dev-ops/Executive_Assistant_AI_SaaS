#!/usr/bin/env python
"""
Create GitHub issues from github-issues-backlog.md.

Defaults to dry-run. Pass --create to actually open issues.
Requires: GitHub CLI (`gh`) already authenticated with repo scope.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BACKLOG = ROOT / "github-issues-backlog.md"
DEFAULT_REPO = "raven-dev-ops/ai_telephony_service_crm"


def clean_text(text: str) -> str:
    """Normalize common mojibake from copied PDF text to ASCII equivalents."""
    replacements = {
        "â€“": "-",  # en dash
        "â€”": "--",  # em dash
        "â€": '"',
        "â€œ": '"',
        "â€™": "'",
        "â€˜": "'",
        "â€¦": "...",
        "â†’": "->",
        "â€": '"',
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def parse_backlog(md_path: Path) -> List[Dict]:
    """Return list of issue dicts from the backlog markdown."""
    raw_text = md_path.read_text(encoding="utf-8")
    text = clean_text(raw_text)

    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
    issues: List[Dict] = []
    for section in sections:
        section = section.strip()
        if not section or not section.startswith("[P"):
            continue

        lines = section.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        # Priority label from [P0]/[P1]/[P2]
        priority_match = re.match(r"\[(P\d)\]", title)
        priority_label = None
        if priority_match:
            priority_label = f"priority/{priority_match.group(1).lower()}"

        labels: List[str] = []
        seen: Set[str] = set()
        for idx, line in enumerate(lines):
            if line.strip().lower().startswith("**suggested labels**"):
                look_ahead = idx + 1
                while look_ahead < len(lines) and lines[look_ahead].strip():
                    for label in re.findall(r"`([^`]+)`", lines[look_ahead]):
                        if label not in seen:
                            labels.append(label)
                            seen.add(label)
                    look_ahead += 1
                break

        if priority_label and priority_label not in seen:
            labels.insert(0, priority_label)

        issues.append({"title": title, "body": body, "labels": labels})
    return issues


def run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def existing_labels(repo: str) -> Set[str]:
    cmd = ["gh", "label", "list", "--repo", repo, "--json", "name", "--limit", "200"]
    result = run(cmd)
    data = json.loads(result.stdout or "[]")
    return {item["name"] for item in data}


def ensure_labels(repo: str, labels: Iterable[str]) -> None:
    colors = {
        # priority
        "priority/p0": "d73a4a",  # red
        "priority/p1": "fbca04",  # yellow
        "priority/p2": "0e8a16",  # green
        # domains
        "security": "d73a4a",
        "reliability": "0366d6",
        "backend": "c5def5",
        "frontend": "bfd4f2",
        "ops": "5319e7",
        "observability": "5319e7",
        "testing": "5319e7",
        "quality": "cfd3d7",
        "tech-debt": "cfd3d7",
        "ux": "c5def5",
        "docs": "c5def5",
    }

    existing = existing_labels(repo)
    for label in labels:
        if label in existing:
            continue
        color = colors.get(label.lower(), "ededed")
        print(f"[label] creating '{label}' ({color})")
        run(["gh", "label", "create", label, "--color", color, "--repo", repo])


def find_issue(repo: str, title: str) -> Tuple[str, str] | None:
    """Return (number, state) if issue with exact title exists."""
    search = f"\"{title}\" in:title"
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--search",
        search,
        "--json",
        "title,number,state",
    ]
    result = run(cmd)
    items = json.loads(result.stdout or "[]")
    for item in items:
        if item["title"].strip().lower() == title.strip().lower():
            return str(item["number"]), item["state"]
    return None


def create_issue(repo: str, issue: Dict, dry_run: bool = True) -> None:
    title = issue["title"]
    body = issue["body"]
    labels = issue.get("labels", [])

    if dry_run:
        print(f"[dry-run] would create: {title} labels={labels}")
        return

    existing = find_issue(repo, title)
    if existing:
        number, state = existing
        print(f"[skip] issue already exists #{number} ({state}): {title}")
        return

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md", encoding="utf-8") as tmp:
        tmp.write(body)
        body_path = tmp.name

    cmd = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", body_path]
    for label in labels:
        cmd.extend(["--label", label])

    print(f"[create] {title}")
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create GitHub issues from backlog markdown.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="target repo (owner/name)")
    parser.add_argument("--path", default=str(DEFAULT_BACKLOG), help="path to backlog markdown")
    parser.add_argument(
        "--create", action="store_true", help="actually create issues (default is dry-run)",
    )
    args = parser.parse_args()

    backlog_path = Path(args.path)
    if not backlog_path.exists():
        sys.exit(f"Backlog file not found: {backlog_path}")

    issues = parse_backlog(backlog_path)
    if not issues:
        sys.exit("No issues found in backlog file.")

    all_labels: Set[str] = set()
    for issue in issues:
        all_labels.update(issue.get("labels", []))

    ensure_labels(args.repo, all_labels)

    for issue in issues:
        create_issue(args.repo, issue, dry_run=not args.create)


if __name__ == "__main__":
    main()
