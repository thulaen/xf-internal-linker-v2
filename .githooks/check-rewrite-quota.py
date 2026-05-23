#!/usr/bin/env python3
"""
Pre-commit hook: enforce the Rewrite Quota rule (2026-05-23, Phase K.2).

Every code-changing commit must produce at least three rewrites or
refactorings that improve the modular monolith. The agent emits a
`[REWRITE COUNT: rewrites=<N> refactorings=<M> total=<N+M>]` marker
in the AGENT-HANDOFF entry. When `total < 3`, the agent may release
the hard block with a `[REWRITE QUOTA EXEMPTION: ...]` marker pointing
at a JSON evidence file under `docs/rewrite-evidence/<session-id>.json`
that `manage.py verify_rewrite_exemption` cross-checks.

Bootstrap exemption: `[REWRITE QUOTA BOOTSTRAP: commit=introduces-rule]`
on the single commit that introduces the rule itself.

Pure-docs commits (no files under backend/, frontend/, services/,
scripts/, .githooks/, docs/specs/, docs/adr/) are exempt.

Full spec at docs/specs/fr-rewrite-quota-and-exemption.md.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 2026-05-23 — Phase K.3 DRY refactor: CODE_PREFIXES and
# staged_code_files were duplicated literally between this hook and
# check-sticky-1-read.py. The shared module owns both now so a future
# code-bearing path under backend/, services/, etc. lands in one
# location.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hook_helpers  # noqa: E402

_REWRITE_COUNT_RE = re.compile(
    r"\[REWRITE\s+COUNT:\s*"
    r"rewrites=(?P<rewrites>\d+)\s+"
    r"refactorings=(?P<refactorings>\d+)\s+"
    r"total=(?P<total>\d+)\]"
)

_BOOTSTRAP_RE = re.compile(
    r"\[REWRITE\s+QUOTA\s+BOOTSTRAP:\s*commit=introduces-rule\]"
)

_EXEMPTION_RE = re.compile(
    r"\[REWRITE\s+QUOTA\s+EXEMPTION:\s*"
    r"touched_area=(?P<touched_area>[^\s]+)\s+"
    r"python_lines_remaining=\d+\s+"
    r"baseline=[^\s]+\s+"
    r"projected_after=[^\s]+\s+"
    r"projected_gain_pct=[0-9.]+\s+"
    r"threshold_pct=[0-9.]+\s+"
    r"verdict=tiny_gain_or_no_python_remains\s+"
    r"evidence_file=(?P<evidence_file>[^\]\s]+)\]"
)

_MIN_QUOTA = 3


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _staged_code_files() -> list[str]:
    """Thin adapter so the in-module function name stays stable for tests."""
    return _hook_helpers.staged_code_files(REPO_ROOT)


def _staged_handoff_diff() -> str:
    """Thin adapter so the in-module function name stays stable for tests."""
    return _hook_helpers.get_staged_handoff_diff(REPO_ROOT)


def _verify_exemption(touched_areas: list[str], evidence_file: str) -> tuple[bool, str]:
    """Run manage.py verify_rewrite_exemption; return (passed, stderr)."""
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "backend",
        "python",
        "manage.py",
        "verify_rewrite_exemption",
        "--evidence-file",
        evidence_file,
    ]
    for area in touched_areas:
        cmd.extend(["--area", area])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"verify_rewrite_exemption could not be invoked: {exc}"
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or "").strip() or (result.stdout or "").strip()


def main() -> int:
    code_files = _staged_code_files()
    if not code_files:
        # Pure-docs commits are exempt.
        return 0

    handoff_text = _staged_handoff_diff()

    if _BOOTSTRAP_RE.search(handoff_text):
        return 0

    count_match = _REWRITE_COUNT_RE.search(handoff_text)
    if count_match:
        rewrites = int(count_match.group("rewrites"))
        refactorings = int(count_match.group("refactorings"))
        supplied_total = int(count_match.group("total"))
        if supplied_total != rewrites + refactorings:
            return _fail(
                "FAIL check-rewrite-quota: marker says "
                f"total={supplied_total} but rewrites + refactorings = "
                f"{rewrites + refactorings}. Fix the marker arithmetic.\n"
            )
        if supplied_total >= _MIN_QUOTA:
            return 0
    else:
        return _fail(
            "FAIL check-rewrite-quota: code-changing commit but the "
            "AGENT-HANDOFF.md entry is missing the [REWRITE COUNT: "
            "rewrites=<N> refactorings=<M> total=<N+M>] marker.\n"
            "WHY: the 2026-05-23 Rewrite Quota rule requires every "
            "code-changing session to produce at least three rewrites "
            "or refactorings that improve the modular monolith, OR "
            "an explicit [REWRITE QUOTA EXEMPTION: ...] marker with a "
            "JSON evidence file. See docs/specs/fr-rewrite-quota-and-"
            "exemption.md.\n"
            "UNBLOCK: add the marker after counting the rewrites and "
            "refactorings in this commit. A rewrite is a replacement of "
            "a legacy implementation with a typed implementation in the "
            "correct owner language. A refactoring is an in-language "
            "structural improvement that preserves behavior.\n"
        )

    # total < 3 — look for the exemption marker.
    exemption_match = _EXEMPTION_RE.search(handoff_text)
    if exemption_match is None:
        return _fail(
            f"FAIL check-rewrite-quota: rewrite count "
            f"{count_match.group('total')} is below the minimum of "
            f"{_MIN_QUOTA} and no [REWRITE QUOTA EXEMPTION: ...] "
            "marker is present.\n"
            "WHY: every code-changing session must produce at least "
            f"{_MIN_QUOTA} rewrites or refactorings, OR provide "
            "deterministic evidence that further rewrites in the "
            "touched area are not justified.\n"
            "UNBLOCK option A: produce more rewrites or refactorings "
            "in this commit until total >= 3, update the marker, and "
            "re-run the commit.\n"
            "UNBLOCK option B: create a JSON evidence file under "
            "docs/rewrite-evidence/<session-id>.json per "
            "docs/specs/fr-rewrite-quota-and-exemption.md and add the "
            "[REWRITE QUOTA EXEMPTION: ...] marker referencing it.\n"
        )

    # Validate the exemption via the management command.
    touched = exemption_match.group("touched_area").split(",")
    evidence_file = exemption_match.group("evidence_file")
    passed, stderr_text = _verify_exemption(touched, evidence_file)
    if passed:
        return 0
    return _fail(
        "FAIL check-rewrite-quota: [REWRITE QUOTA EXEMPTION: ...] "
        f"marker refused by verify_rewrite_exemption.\n"
        f"VERIFIER OUTPUT: {stderr_text}\n"
        "UNBLOCK: fix the evidence file per the message above and "
        "re-run the commit.\n"
    )


if __name__ == "__main__":
    sys.exit(main())
