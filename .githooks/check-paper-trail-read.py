#!/usr/bin/env python3
"""Pre-commit gate for the paper-trail opening ritual.

Validates that the newly staged AGENT-HANDOFF.md entry contains:
  - a [PAPER TRAIL READ: ...] marker with the 16-category breakdown
  - the breakdown numbers sum to N (the declared open count)
  - exactly 10 picked ids (or a drought-substitution form)
  - a [PAPER TRAIL QUOTA VERIFIED: 10 resolved] marker, plus shells out
    to manage.py verify_paper_trail_quota to confirm the 10 ids are
    really resolved with two-part lessons.

Exit codes:
  0 — pass (or no staged files)
  1 — reserved for old pass-but-warn behavior
  2 — hard fail (commit blocked)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDOFF_PATH = REPO_ROOT / "AGENT-HANDOFF.md"

# The 16 categories in the canonical order print_open_paper_trail emits.
_CATEGORIES = (
    "autoissue_deferral",
    "cve_upgrade",
    "coverage_gap",
    "infrastructure",
    "ruff_sweep",
    "mutation_survivor",
    "debt_reduction",
    "feature_decision",
    "tooling_gap",
    "documentation",
    "dependency_upgrade",
    "refactor",
    "performance",
    "security",
    "accessibility",
    "other",
)

# Match the full marker: [PAPER TRAIL READ: <N> open (<a> autoissue_deferral / ...) — picked: ...]
_MARKER_RE = re.compile(
    r"\[PAPER\s+TRAIL\s+READ:\s*(?P<n>\d+)\s+open\s*\((?P<breakdown>[^)]+)\)\s*"
    r"(?:—|--|-)\s*picked:\s*(?P<picks>[^\]]+)\]",
    re.IGNORECASE,
)
_QUOTA_VERIFIED_RE = re.compile(
    r"\[PAPER\s+TRAIL\s+QUOTA\s+VERIFIED:\s*10\s+resolved\]",
    re.IGNORECASE,
)
_BREAKDOWN_TOKEN_RE = re.compile(r"(\d+)\s+(\w+)")
_ID_RE = re.compile(r"#(\d+)")
_DROUGHT_RE = re.compile(r"drought", re.IGNORECASE)
_FORBIDDEN_SATISFIER_RE = re.compile(
    r"auto-defer-10\s+satisfier",
    re.IGNORECASE,
)
# Code-changing path prefixes.
_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
    "backend/extensions/",
)


# _read_staged_handoff_diff() lives in _hook_helpers.py per paper-trail
# #585 / test_case #703. The shared helper already filters to added
# lines and uses utf-8/errors=replace.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import get_staged_handoff_diff  # noqa: E402


def _read_staged_handoff_diff() -> str:
    return get_staged_handoff_diff(REPO_ROOT)


def _code_changing_commit() -> bool:
    files = _staged_files()
    return any(f.startswith(_CODE_PREFIXES) for f in files)


def _staged_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _commit_has_staged_files() -> bool:
    return bool(_staged_files())


def _validate_marker(added: str) -> tuple[int, list[int]]:
    """Validate the marker. Returns (exit_code, picked_ids)."""
    if _FORBIDDEN_SATISFIER_RE.search(added):
        sys.stderr.write(
            "FAIL check-paper-trail-read: the phrase 'auto-defer-10 satisfier' "
            "is forbidden in handoff entries. Resolve real paper-trail items.\n"
        )
        return 2, []

    match = _MARKER_RE.search(added)
    if not match:
        sys.stderr.write(
            "FAIL check-paper-trail-read: AGENT-HANDOFF.md is missing the "
            "[PAPER TRAIL READ: <N> open (<a> autoissue_deferral / ... / <p> other) "
            "— picked: #..., ...] marker. Run "
            "`docker compose exec -T backend python manage.py print_open_paper_trail` "
            "and paste the output into the new handoff entry.\n"
        )
        return 2, []

    declared_n = int(match["n"])
    breakdown_text = match["breakdown"]
    tokens = _BREAKDOWN_TOKEN_RE.findall(breakdown_text)
    by_cat = {cat: int(n) for n, cat in tokens}

    missing = [cat for cat in _CATEGORIES if cat not in by_cat]
    if missing:
        sys.stderr.write(
            f"FAIL check-paper-trail-read: marker breakdown is missing categories: "
            f"{', '.join(missing)}. All 16 must be listed.\n"
        )
        return 2, []

    bucket_sum = sum(by_cat[cat] for cat in _CATEGORIES)
    if bucket_sum != declared_n:
        sys.stderr.write(
            f"FAIL check-paper-trail-read: per-category breakdown sums to "
            f"{bucket_sum} but the marker declares {declared_n} open.\n"
        )
        return 2, []

    ids = [int(m) for m in _ID_RE.findall(match["picks"])]
    drought = bool(_DROUGHT_RE.search(match["picks"]))
    # Docs-only commits accept the drought form (the picker honestly
    # showed fewer than 10 open entries). Code-changing commits hit the
    # _verify_quota gate next which rejects drought-form outright.
    if not drought and len(ids) != 10:
        sys.stderr.write(
            f"FAIL check-paper-trail-read: expected 10 picked ids "
            f"(or drought-substitution form); got {len(ids)}.\n"
        )
        return 2, []
    if len(set(ids)) != len(ids):
        sys.stderr.write(
            "FAIL check-paper-trail-read: duplicate Paper Trail picked IDs "
            "are not allowed. Pick different paper-trail entries.\n"
        )
        return 2, []

    return 0, ids


def _verify_quota(ids: list[int]) -> int:
    """Shell out to manage.py verify_paper_trail_quota.

    HARD-BLOCK semantics (matches .githooks/check-registry-read.py): the
    quota check MUST run and MUST pass. There is no "skipped" exit code:
    if Docker is unavailable, if the command times out, or if drought form
    is used on a staged commit, the commit FAILS so that the backlog never
    grows silently. Returns 0 on pass, 2 on any failure.
    """
    if len(ids) != 10:
        # Drought form on a staged commit is a HARD FAIL — file
        # new paper-trail entries via `manage.py defer_work` until the
        # picker has 10 to choose from, then resolve those 10.
        sys.stderr.write(
            "FAIL check-paper-trail-read: drought-substitution form is not "
            "allowed on a staged commit. The paper-trail picker found "
            f"only {len(ids)} entr(y/ies); you must file new entries via "
            "`manage.py defer_work --title ... --category ... --abstract ... "
            "--deferred-by ...` until the queue has 10, then resolve those 10 "
            "via `manage.py resolve_paper_trail`.\n"
        )
        return 2

    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_paper_trail_quota",
        "--ids", *[str(i) for i in ids],
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        sys.stderr.write(
            "FAIL check-paper-trail-read: docker is not on PATH. The 10-"
            "paper-trail quota MUST be checked against the live database "
            "before any code-changing commit can land. Start Docker Desktop "
            "and re-run, OR run the same commit on a host where Docker is "
            "available. Skipping this check is forbidden.\n"
        )
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "FAIL check-paper-trail-read: `manage.py verify_paper_trail_quota` "
            "timed out (60s). The 10-paper-trail quota check is required; "
            "wait for the backend stack to be healthy and re-run.\n"
        )
        return 2

    if result.returncode != 0:
        sys.stderr.write(
            "FAIL check-paper-trail-read: "
            "manage.py verify_paper_trail_quota rejected the picks.\n"
            f"{result.stdout}\n{result.stderr}\n"
        )
        return 2

    sys.stdout.write("[PAPER TRAIL QUOTA VERIFIED: 10 resolved]\n")
    return 0


def main() -> int:
    added = _read_staged_handoff_diff()
    if not added:
        # AGENT-HANDOFF.md was not staged. Any staged commit requires
        # Paper Trail proof so docs/tooling commits cannot skip it.
        if _commit_has_staged_files():
            sys.stderr.write(
                "FAIL check-paper-trail-read: this commit has staged files but "
                "does not update AGENT-HANDOFF.md with a [PAPER TRAIL READ: ...] "
                "marker.\n"
                "WHY: Rule (Paper Trail) requires every commit "
                "to surface the picked 10 paper-trail entries up front so "
                "future agents see what's open.\n"
                "UNBLOCK: Run `manage.py print_open_paper_trail` and paste "
                "the marker into a new AGENT-HANDOFF.md entry. Stage the "
                "handoff (`git add AGENT-HANDOFF.md`) and re-commit.\n"
            )
            return 2
        return 0

    exit_code, ids = _validate_marker(added)
    if exit_code != 0:
        return exit_code

    if _commit_has_staged_files() and not _QUOTA_VERIFIED_RE.search(added):
        sys.stderr.write(
            "FAIL check-paper-trail-read: commit is missing the "
            "[PAPER TRAIL QUOTA VERIFIED: 10 resolved] marker. Run "
            "`manage.py verify_paper_trail_quota --ids <10 ids> "
            "--resolved-after <prev handoff timestamp>` and paste the result.\n"
        )
        return 2

    if not _commit_has_staged_files():
        return 0

    return _verify_quota(ids)


if __name__ == "__main__":
    sys.exit(main())
