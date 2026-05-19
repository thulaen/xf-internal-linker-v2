#!/usr/bin/env python3
"""PARAMOUNT — Paper Trail Evidence Rule (added 2026-05-17).

Hard-blocks any commit whose staged AGENT-HANDOFF.md entry references
paper-trail rows (`[PAPER TRAIL FILED: #N]`) that do not satisfy the
Paper Trail Evidence Rule. For each referenced ID this hook shells
`manage.py verify_paper_trail_evidence --paper-trail-id <N>`; a
non-zero exit from any one of them hard-blocks the commit with the
Rule-F three-part error the command emits.

Pre-cutoff entries (deferred_at < 2026-05-17T07:25:00Z) pass via the
verifier's grandfather branch; post-cutoff entries must have a
test_case AutoIssue link with all 10 BDD fields AND a non-empty
citations list with every entry matching an accepted citation form.

Spec: docs/PAPER-TRAIL-EVIDENCE-RULE.md
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

# `[PAPER TRAIL FILED: #N]` is the marker emitted by manage.py defer_work.
_PAPER_TRAIL_FILED_RE = re.compile(
    r"\[PAPER\s+TRAIL\s+FILED:\s*#(?P<id>\d+)\s*\]",
    re.IGNORECASE,
)


def extract_paper_trail_ids(diff: str) -> list[int]:
    """Return the list of unique paper-trail IDs in the diff, in first-seen order."""
    seen: dict[int, None] = {}
    for m in _PAPER_TRAIL_FILED_RE.finditer(diff or ""):
        try:
            seen.setdefault(int(m.group("id")), None)
        except ValueError:  # pragma: no cover — regex guards against this
            continue
    return list(seen.keys())


def _real_verifier(paper_trail_id: int) -> int:
    """Default per-ID verifier (legacy path; retained for test injection)."""
    return _real_batch_verifier([paper_trail_id])


def _real_batch_verifier(paper_trail_ids: list[int]) -> int:
    """Batch verifier — shells `manage.py verify_paper_trail_evidence --ids`.

    2026-05-17 — paper-trail #588 Quick win #5. Replaces N docker-exec
    startups (~2-3 s each) with one (~2-3 s total). On a 50-marker
    staged commit this cuts hook runtime from ~100 s to ~3 s.

    The verifier loops over every ID and aggregates errors; a single
    failing ID still hard-blocks the commit. The CommandError raised
    by the backend command contains all the failures concatenated.
    """
    if not paper_trail_ids:
        return 0
    csv = ",".join(str(pk) for pk in paper_trail_ids)
    try:
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "backend",
                "python", "manage.py", "verify_paper_trail_evidence",
                "--ids", csv,
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            # Generous timeout for the batched call: 30s base + 1s per ID
            # so a 100-ID commit gets 130 s. Most commits land under 5 s.
            timeout=30 + len(paper_trail_ids),
            check=False,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stdout + result.stderr)
        return result.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(
            f"FAIL check-paper-trail-evidence: could not run "
            f"manage.py verify_paper_trail_evidence --ids ({exc}). "
            f"Docker may be down or the verify command missing.\n"
            f"WHY: the rule cannot be enforced without the verifier.\n"
            f"UNBLOCK: start Docker, ensure the backend container is "
            f"running, then re-stage the commit.\n"
        )
        return 2


def validate_markers(
    diff: str,
    verifier: Callable[[int], int] | None = None,
    batch_verifier: Callable[[list[int]], int] | None = None,
) -> int:
    """Validate every [PAPER TRAIL FILED: #N] marker in the diff.

    Returns 0 on pass, 2 on fail. Either `verifier` (per-ID, legacy) or
    `batch_verifier` (preferred) can be injected for tests. Production
    callers leave both as None and the real batch verifier is used.
    """
    ids = extract_paper_trail_ids(diff)
    if not ids:
        return 0
    # Prefer batch path for production + new tests; fall back to per-ID
    # if only the legacy verifier is injected.
    if batch_verifier is not None:
        rc = batch_verifier(ids)
        return 0 if rc == 0 else 2
    if verifier is not None:
        for pt_id in ids:
            rc = verifier(pt_id)
            if rc != 0:
                return 2
        return 0
    rc = _real_batch_verifier(ids)
    return 0 if rc == 0 else 2


# _read_staged_handoff_diff() lives in _hook_helpers.py per paper-trail
# #585 / test_case #703.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import get_staged_handoff_diff  # noqa: E402


def _read_staged_handoff_diff() -> str:
    return get_staged_handoff_diff(REPO_ROOT)


def main() -> int:
    diff = _read_staged_handoff_diff()
    return validate_markers(diff, verifier=None)


if __name__ == "__main__":
    sys.exit(main())
