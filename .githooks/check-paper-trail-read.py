#!/usr/bin/env python3
"""Pre-commit gate for the paper-trail opening ritual + resolution quota.

Lowered + broadened on 2026-05-16:
  - The resolution quota is now 3 picks per session (was 10).
  - The quota fires on EVERY commit, not just code-changing commits.
    A docs-only typo fix must still resolve 3 paper-trail entries.

Validates the staged AGENT-HANDOFF.md added lines contain:
  - a `[PAPER TRAIL READ: <N> open (...) — picked: #..., #..., #...]`
    marker with the 16-category breakdown summing to N
  - exactly 3 picked ids (drought-substitution form is rejected — file
    new entries via `manage.py defer_work` until the picker has 3)
  - a `[PAPER TRAIL QUOTA VERIFIED: 3 resolved]` marker
  - the DB confirms the 3 picks are resolved with two-part lessons
    (via `manage.py verify_paper_trail_quota`)

Exit codes:
  0 — pass
  2 — hard fail (commit blocked)

Rule F compliant: every FAIL message has WHY + UNBLOCK.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDOFF_PATH = REPO_ROOT / "AGENT-HANDOFF.md"

# Required quota: lowered from 10 to 3 on 2026-05-16.
_REQUIRED_QUOTA = 3

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

# Match: [PAPER TRAIL READ: <N> open (<a> autoissue_deferral / ...) — picked: ...]
_MARKER_RE = re.compile(
    r"\[PAPER\s+TRAIL\s+READ:\s*(?P<n>\d+)\s+open\s*\((?P<breakdown>[^)]+)\)\s*"
    r"(?:—|--|-)\s*picked:\s*(?P<picks>[^\]]+)\]",
    re.IGNORECASE,
)
_QUOTA_VERIFIED_RE = re.compile(
    rf"\[PAPER\s+TRAIL\s+QUOTA\s+VERIFIED:\s*{_REQUIRED_QUOTA}\s+resolved\]",
    re.IGNORECASE,
)
_BREAKDOWN_TOKEN_RE = re.compile(r"(\d+)\s+(\w+)")
_ID_RE = re.compile(r"#(\d+)")
_DROUGHT_RE = re.compile(r"drought", re.IGNORECASE)
# Both the legacy "auto-defer-10 satisfier" and the new "auto-defer-3
# satisfier" phrases are forbidden — agents must not farm trivial
# entries to clear the quota.
_FORBIDDEN_SATISFIER_RE = re.compile(
    r"auto-defer-(?:10|3)\s+satisfier",
    re.IGNORECASE,
)


def _read_staged_handoff_diff() -> str:
    """Return the added lines from the staged diff of AGENT-HANDOFF.md."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--", "AGENT-HANDOFF.md"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return "\n".join(
        line[1:]
        for line in (result.stdout or "").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _has_any_staged_files() -> bool:
    """True if anything is staged (any commit, not just code-changing)."""
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
        return False
    return bool((result.stdout or "").strip())


def _validate_marker(added: str) -> tuple[int, list[int]]:
    """Validate the marker. Returns (exit_code, picked_ids)."""
    if _FORBIDDEN_SATISFIER_RE.search(added):
        sys.stderr.write(
            "FAIL check-paper-trail-read: the phrase 'auto-defer-3 satisfier' "
            "(or the legacy 'auto-defer-10 satisfier') is forbidden in handoff "
            "entries.\n"
            "WHY: That phrase historically signalled an agent farming trivial "
            "deferrals to clear the quota gate. Real paper-trail items must "
            "be resolved.\n"
            "UNBLOCK: Resolve the actual picked entries via "
            "`manage.py resolve_paper_trail --id <N> --lessons-learned "
            "\"Trap: ... Fix shape: ...\"`.\n"
        )
        return 2, []

    match = _MARKER_RE.search(added)
    if not match:
        sys.stderr.write(
            "FAIL check-paper-trail-read: AGENT-HANDOFF.md is missing the "
            "[PAPER TRAIL READ: <N> open (<a> autoissue_deferral / ... / <p> other) "
            "— picked: #..., #..., #...] marker.\n"
            "WHY: Every commit (lowered + broadened 2026-05-16) must "
            f"resolve {_REQUIRED_QUOTA} picked paper-trail entries, and the "
            "marker is the proof that the agent saw the picks.\n"
            "UNBLOCK: Run `docker compose exec -T backend python manage.py "
            "print_open_paper_trail` and paste the printed marker into the "
            "new handoff entry; resolve the 3 picks via "
            "`manage.py resolve_paper_trail` before committing.\n"
        )
        return 2, []

    declared_n = int(match["n"])
    breakdown_text = match["breakdown"]
    tokens = _BREAKDOWN_TOKEN_RE.findall(breakdown_text)
    by_cat = {cat: int(n) for n, cat in tokens}

    missing = [cat for cat in _CATEGORIES if cat not in by_cat]
    if missing:
        sys.stderr.write(
            "FAIL check-paper-trail-read: marker breakdown is missing categories: "
            f"{', '.join(missing)}. All 16 must be listed.\n"
            "WHY: The breakdown is what tells the next agent which category "
            "is heaviest and where new deferrals are stacking up.\n"
            "UNBLOCK: Re-run `manage.py print_open_paper_trail` and paste the "
            "full marker (do not edit the breakdown).\n"
        )
        return 2, []

    bucket_sum = sum(by_cat[cat] for cat in _CATEGORIES)
    if bucket_sum != declared_n:
        sys.stderr.write(
            "FAIL check-paper-trail-read: per-category breakdown sums to "
            f"{bucket_sum} but the marker declares {declared_n} open.\n"
            "WHY: A mismatched breakdown means the marker was hand-edited "
            "or copied from a stale session.\n"
            "UNBLOCK: Re-run `manage.py print_open_paper_trail` and paste the "
            "fresh marker verbatim.\n"
        )
        return 2, []

    ids = [int(m) for m in _ID_RE.findall(match["picks"])]
    drought = bool(_DROUGHT_RE.search(match["picks"]))
    if drought:
        sys.stderr.write(
            "FAIL check-paper-trail-read: drought-substitution form is not "
            f"allowed. The paper-trail picker found only {len(ids)} entr"
            f"(y/ies); you must file new entries until the queue has "
            f"{_REQUIRED_QUOTA}, then resolve those {_REQUIRED_QUOTA}.\n"
            "WHY: The whole point of the per-session quota is to keep the "
            "backlog under control; accepting drought form would let it grow "
            "silently.\n"
            "UNBLOCK: Run `docker compose exec -T backend python manage.py "
            "defer_work --title ... --category ... --abstract \"Given ... "
            "When ... Then ...\" --deferred-by <agent> --risk-on-inaction "
            "\"...\" --acceptance-criteria \"...\"` until the picker has "
            f"{_REQUIRED_QUOTA}, then re-run `print_open_paper_trail` and "
            "resolve those picks.\n"
        )
        return 2, []
    if len(ids) != _REQUIRED_QUOTA:
        sys.stderr.write(
            f"FAIL check-paper-trail-read: expected {_REQUIRED_QUOTA} picked "
            f"ids; got {len(ids)}.\n"
            "WHY: The quota was lowered from 10 to 3 on 2026-05-16 and now "
            "fires on every commit. The marker must show exactly "
            f"{_REQUIRED_QUOTA} ids.\n"
            "UNBLOCK: Re-run `manage.py print_open_paper_trail` (default "
            f"--limit={_REQUIRED_QUOTA}) and paste the fresh marker.\n"
        )
        return 2, []

    return 0, ids


def _verify_quota(ids: list[int]) -> int:
    """Shell out to manage.py verify_paper_trail_quota.

    HARD-BLOCK semantics: the quota check MUST run and MUST pass. There
    is no "skipped" exit code: if Docker is unavailable or the command
    times out, the commit FAILS so the backlog never grows silently.
    """
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_paper_trail_quota",
        "--ids", *[str(i) for i in ids],
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        sys.stderr.write(
            "FAIL check-paper-trail-read: docker is not on PATH.\n"
            f"WHY: The {_REQUIRED_QUOTA}-paper-trail quota MUST be checked "
            "against the live database before any commit can land.\n"
            "UNBLOCK: Start Docker Desktop and re-run the commit, or run "
            "the same commit on a host where Docker is available. Skipping "
            "this check is forbidden.\n"
        )
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "FAIL check-paper-trail-read: `manage.py verify_paper_trail_quota` "
            "timed out (60s).\n"
            f"WHY: The {_REQUIRED_QUOTA}-paper-trail quota check is required "
            "for every commit and the backend stack is not responding.\n"
            "UNBLOCK: Wait for the backend stack to become healthy "
            "(`docker compose ps` should show backend = healthy), then re-run "
            "the commit.\n"
        )
        return 2

    if result.returncode != 0:
        sys.stderr.write(
            "FAIL check-paper-trail-read: "
            "manage.py verify_paper_trail_quota rejected the picks.\n"
            f"WHY: One or more of the {_REQUIRED_QUOTA} picked entries is "
            "not resolved, has no `resolved_at` timestamp, was resolved "
            "before the previous handoff, or has malformed "
            "`resolution_lessons` (missing `Trap:` or `Fix shape:` part).\n"
            "UNBLOCK: Read the command output below for the specific row(s) "
            "that failed and fix each via `manage.py resolve_paper_trail "
            "--id <N> --lessons-learned \"Trap: ... Fix shape: ...\"`.\n"
            f"{result.stdout}\n{result.stderr}\n"
        )
        return 2

    sys.stdout.write(
        f"[PAPER TRAIL QUOTA VERIFIED: {_REQUIRED_QUOTA} resolved]\n"
    )
    return 0


def main() -> int:
    # If nothing is staged at all there's no commit happening — skip.
    if not _has_any_staged_files():
        return 0

    added = _read_staged_handoff_diff()
    if not added:
        sys.stderr.write(
            "FAIL check-paper-trail-read: this commit does not update "
            "AGENT-HANDOFF.md.\n"
            "WHY: As of 2026-05-16 every commit (not just code-changing "
            "ones) must include a fresh AGENT-HANDOFF.md entry carrying the "
            "[PAPER TRAIL READ: ...] marker and the resolved-quota proof. "
            "Docs-only and typo-fix commits are no longer exempt — the goal "
            "is steady backlog drain on every commit, not only on big ones.\n"
            "UNBLOCK: Run `docker compose exec -T backend python manage.py "
            "print_open_paper_trail`, append a new entry to "
            "AGENT-HANDOFF.md with the printed marker, resolve the "
            f"{_REQUIRED_QUOTA} picks via `manage.py resolve_paper_trail`, "
            f"include the `[PAPER TRAIL QUOTA VERIFIED: {_REQUIRED_QUOTA} "
            "resolved]` marker, stage the handoff, and re-commit.\n"
        )
        return 2

    exit_code, ids = _validate_marker(added)
    if exit_code != 0:
        return exit_code

    if not _QUOTA_VERIFIED_RE.search(added):
        sys.stderr.write(
            "FAIL check-paper-trail-read: missing the "
            f"[PAPER TRAIL QUOTA VERIFIED: {_REQUIRED_QUOTA} resolved] "
            "marker.\n"
            "WHY: The marker is the agent's claim that the picks are "
            "resolved; the hook independently verifies that claim against "
            "the database in the next step.\n"
            "UNBLOCK: Run `docker compose exec -T backend python manage.py "
            f"verify_paper_trail_quota --ids {' '.join(str(i) for i in ids)} "
            "--resolved-after <prev handoff timestamp>` and paste the "
            "printed marker into the handoff entry.\n"
        )
        return 2

    return _verify_quota(ids)


if __name__ == "__main__":
    sys.exit(main())
