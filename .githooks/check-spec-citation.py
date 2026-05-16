#!/usr/bin/env python3
"""Pre-commit gate for Rule C (spec citations).

Fires when a new docs/specs/*.md file is staged. Validates at least one
[SPEC CITED] marker is present in the spec file. Rule F: plain-English FAIL.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SPEC_CITED_RE = re.compile(
    r"\[SPEC CITED:\s*feature=([^\s]+)\s+kind=(\w+)\s+id=(\S+)\s+verified_at=([^\]]+)\]"
)


def _staged_new_specs() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [
        line.strip()
        for line in (out.stdout or "").splitlines()
        if line.strip().startswith("docs/specs/")
        and line.strip().endswith(".md")
        and not line.strip().endswith("_spec-template.md")
    ]


def main() -> int:
    specs = _staged_new_specs()
    if not specs:
        return 0
    missing: list[str] = []
    for spec in specs:
        path = REPO_ROOT / spec
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not _SPEC_CITED_RE.search(text):
            missing.append(spec)
    if missing:
        joined = ", ".join(missing)
        sys.stderr.write(
            f"FAIL check-spec-citation: new spec file(s) without citation: {joined}\n"
            "WHY: Rule C requires every new feature / algorithm / signal / "
            "meta-algorithm parameter to cite at least one patent, DOI, RFC, "
            "or stable URL before implementation begins.\n"
            "UNBLOCK: For each new spec, add at least one citation in the "
            "form `[SPEC CITED: feature=<id> kind=doi id=<reference> "
            "verified_at=<ISO8601>]` and register it via "
            "`manage.py cite_spec --key <kind>:<id> ...`. The CitationCache "
            "sub-index will then resolve the citation on every commit.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
