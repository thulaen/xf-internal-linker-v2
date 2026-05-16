#!/usr/bin/env python3
"""Rule H.H2 — reject local secret / junk / temp files from being committed.

File-scoped: scans the staged file list itself; only fires if any of
the disallowed patterns is present.

Rule F compliant: every FAIL message has WHY + UNBLOCK.

Blocks:
  - Secret stores:    .env, .env.*, *credentials*, *token*, *service_account*
  - Local databases:  *.sqlite3, *.sqlite3-journal, db.sqlite3, test.sqlite3
  - Build / coverage: coverage/, coverage.xml, htmlcov/, .coverage, .pytest_cache/
  - Logs / temp:      *.log, tmp/, .DS_Store, Thumbs.db, *.swp, *.swo
  - Docker local:     docker-compose.override.yml, tmp/docker-config/
  - Editor:           .idea/, .vscode/ (case-by-case; some teams allow)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_JUNK_PATTERNS = (
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"(^|/).*credentials.*\.json$", re.IGNORECASE),
    re.compile(r"(^|/).*service_account.*\.json$", re.IGNORECASE),
    re.compile(r"(^|/).*token.*\.json$", re.IGNORECASE),
    re.compile(r"(^|/).*client_secret.*\.json$", re.IGNORECASE),
    re.compile(r"\.sqlite3(-journal)?$"),
    re.compile(r"(^|/)coverage(\.xml)?$"),
    re.compile(r"(^|/)htmlcov/"),
    re.compile(r"(^|/)\.coverage$"),
    re.compile(r"(^|/)\.pytest_cache/"),
    re.compile(r"\.log$"),
    re.compile(r"(^|/)\.DS_Store$"),
    re.compile(r"(^|/)Thumbs\.db$"),
    re.compile(r"\.swp$"), re.compile(r"\.swo$"),
    re.compile(r"(^|/)tmp/"),
    re.compile(r"(^|/)docker-compose\.override\.yml$"),
)


def _staged_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in (out.stdout or "").splitlines() if line.strip()]


def main() -> int:
    files = _staged_files()
    if not files:
        return 0
    hits: list[str] = []
    for f in files:
        for pat in _JUNK_PATTERNS:
            if pat.search(f):
                hits.append(f)
                break
    if not hits:
        return 0
    sys.stderr.write(
        "FAIL check-junk-files: staged files include local-only / "
        "secret / junk patterns that should never be committed.\n"
        "WHY: Rule H.H2 blocks .env, *.sqlite3, *.log, coverage/, "
        ".DS_Store, .swp, tmp/, credentials.json, service_account.json, "
        "docker-compose.override.yml, and other per-developer artefacts "
        "from reaching the repo. Committing secrets can leak credentials; "
        "committing local DBs and logs bloats history.\n"
        "UNBLOCK: `git rm --cached <file>` for each match, then add the "
        "pattern to `.gitignore` so it stays out. If the file is "
        "legitimately repo-tracked (rare), file a false-positive report:\n"
        "  docker compose exec -T backend python manage.py "
        "report_hook_false_positive --hook check-junk-files "
        "--context \"<explanation>\"\n"
    )
    for h in hits:
        sys.stderr.write(f"  blocked: {h}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
