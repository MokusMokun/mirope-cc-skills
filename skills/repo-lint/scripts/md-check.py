#!/usr/bin/env python3
"""
Markdown checker for repo-lint skill. Stdlib only.

Two checks:
  1. trailing whitespace / hard tabs on any line
  2. relative links pointing to a path that doesn't exist on disk

Usage:
  md-check.py [ROOT]

  ROOT defaults to current working directory. Walks recursively, skipping
  .git/ and any directory named node_modules.

Exit code: 0 if no issues, 1 if any issue found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}
RELATIVE_LINK_RE = re.compile(r"\]\((\.[^)\s#]+)(?:#[^)]*)?\)")


def iter_md(root: Path):
    for p in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def check_whitespace(path: Path) -> list[str]:
    issues = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.rstrip("\n")
        if stripped != stripped.rstrip(" \t"):
            issues.append(f"{path}:{n}: trailing whitespace")
        if "\t" in stripped:
            issues.append(f"{path}:{n}: hard tab")
    return issues


def check_links(path: Path) -> list[str]:
    issues = []
    text = path.read_text()
    for m in RELATIVE_LINK_RE.finditer(text):
        target = (path.parent / m.group(1)).resolve()
        if not target.exists():
            line = text[: m.start()].count("\n") + 1
            issues.append(f"{path}:{line}: broken relative link -> {m.group(1)}")
    return issues


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.exists():
        print(f"error: {root} does not exist", file=sys.stderr)
        return 2

    all_issues: list[str] = []
    files_checked = 0
    for md in iter_md(root):
        files_checked += 1
        all_issues.extend(check_whitespace(md))
        all_issues.extend(check_links(md))

    print(f"md-check: scanned {files_checked} markdown file(s) under {root}")
    if all_issues:
        print(f"  {len(all_issues)} issue(s):")
        for line in all_issues:
            print(f"  {line}")
        return 1
    print("  clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
