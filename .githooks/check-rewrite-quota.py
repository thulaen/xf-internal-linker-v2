#!/usr/bin/env python3
"""
Pre-commit hook: enforce the Rewrite Quota rule (2026-05-23, Phase K.2).

Every code-changing commit must produce improvements across 20 categories,
each requiring a minimum of 15 items (300 total). The agent emits a
`[REWRITE COUNT: rewrites=<N> refactorings=<M> ... total=<sum>]` marker
in the AGENT-HANDOFF entry. When `total < 300`, the agent may release
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hook_helpers  # noqa: E402

# --- Category definitions ---------------------------------------------------
# Each tuple: (field_name, min_required, plain_english_description)
_CATEGORIES = (
    ("rewrites", 15,
     "replacing legacy code with typed code in the correct owner language"),
    ("refactorings", 15,
     "in-language structural improvements that preserve behavior"),
    ("long_functions_fixed", 15,
     "shortening functions over 50 lines to ≤50 lines"),
    ("dead_code_removed", 15,
     "unused imports, unreachable branches, orphaned functions deleted"),
    ("duplicates_eliminated", 15,
     "copy-pasted blocks (6+ lines) consolidated into shared helpers"),
    ("magic_numbers_named", 15,
     "raw literals replaced with named constants or enums"),
    ("type_annotations_added", 15,
     "functions/variables given proper type hints or stricter types"),
    ("docstrings_added", 15,
     "public functions/classes given proper documentation"),
    ("error_handling_improved", 15,
     "bare except or swallowed errors replaced with specific handling"),
    ("boundary_violations_fixed", 15,
     "cross-module imports moved through api.py"),
    ("circular_dependencies_broken", 15,
     "import cycles resolved"),
    ("god_classes_split", 15,
     "classes with too many responsibilities broken into focused ones"),
    ("n_plus_one_queries_fixed", 15,
     "ORM queries in loops replaced with select_related/prefetch_related"),
    ("unbounded_queries_paginated", 15,
     "queryset .all() calls given limits or pagination"),
    ("missing_indexes_added", 15,
     "database indexes added where queries were doing full table scans"),
    ("missing_tests_added", 15,
     "untested public functions given their first test"),
    ("flaky_tests_stabilized", 15,
     "non-deterministic tests made reliable"),
    ("hardcoded_secrets_removed", 15,
     "credentials moved to env vars or secrets manager"),
    ("sql_injections_parameterized", 15,
     "string-formatted queries replaced with parameterized ones"),
    ("complexity_reduced", 15,
     "functions with cyclomatic complexity >10 simplified to ≤10"),
)

_MIN_QUOTA = sum(c[1] for c in _CATEGORIES)  # 300
_CATEGORY_COUNT = len(_CATEGORIES)

# Build the regex dynamically from the category list.
_field_patterns = [
    rf"(?P<{name}>\d+)" for name, _, _ in _CATEGORIES
]
_REWRITE_COUNT_RE = re.compile(
    r"\[REWRITE\s+COUNT:\s*"
    + r"\s+".join(
        rf"{name}={pattern}"
        for (name, _, _), pattern in zip(_CATEGORIES, _field_patterns)
    )
    + r"\s+total=(?P<total>\d+)\]"
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


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _staged_code_files() -> list[str]:
    """Thin adapter so the in-module function name stays stable."""
    return _hook_helpers.staged_code_files(REPO_ROOT)


def _staged_handoff_diff() -> str:
    """Thin adapter so the in-module function name stays stable."""
    return _hook_helpers.get_staged_handoff_diff(REPO_ROOT)


def _category_names() -> list[str]:
    return [name for name, _, _ in _CATEGORIES]


def _marker_template() -> str:
    fields = " ".join(f"{name}=<N>" for name in _category_names())
    return f"[REWRITE COUNT: {fields} total=<sum>]"


def _category_summary() -> str:
    lines = []
    for name, minimum, desc in _CATEGORIES:
        lines.append(f"  {name} (≥{minimum}): {desc}")
    return "\n".join(lines)


def _verify_exemption_marker(handoff_text: str) -> tuple[bool, str]:
    exemption_match = _EXEMPTION_RE.search(handoff_text)
    if exemption_match is None:
        return False, ""
    touched = exemption_match.group("touched_area").split(",")
    evidence_file = exemption_match.group("evidence_file")
    return _verify_exemption(touched, evidence_file)


def _verify_exemption(
    touched_areas: list[str], evidence_file: str,
) -> tuple[bool, str]:
    """Run manage.py verify_rewrite_exemption."""
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_rewrite_exemption",
        "--evidence-file", evidence_file,
    ]
    for area in touched_areas:
        cmd.extend(["--area", area])
    try:
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=30, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"verify_rewrite_exemption failed: {exc}"
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or "").strip() or (result.stdout or "").strip()


def main() -> int:
    code_files = _staged_code_files()
    if not code_files:
        return 0

    handoff_text = _staged_handoff_diff()

    if _BOOTSTRAP_RE.search(handoff_text):
        return 0

    count_match = _REWRITE_COUNT_RE.search(handoff_text)
    if count_match:
        values: dict[str, int] = {}
        for name, _, _ in _CATEGORIES:
            values[name] = int(count_match.group(name))

        supplied_total = int(count_match.group("total"))
        computed_total = sum(values.values())

        if supplied_total != computed_total:
            return _fail(
                "FAIL check-rewrite-quota: marker says "
                f"total={supplied_total} but the {_CATEGORY_COUNT} fields sum to "
                f"{computed_total}. Fix the marker arithmetic.\n"
            )

        if supplied_total < _MIN_QUOTA:
            passed, stderr_text = _verify_exemption_marker(handoff_text)
            if passed:
                return 0
            if _EXEMPTION_RE.search(handoff_text):
                return _fail(
                    "FAIL check-rewrite-quota: [REWRITE QUOTA EXEMPTION: ...] "
                    "marker refused by verify_rewrite_exemption.\n"
                    f"VERIFIER OUTPUT: {stderr_text}\n"
                    "UNBLOCK: fix the evidence file per the message above.\n"
                )
            return _fail(
                "FAIL check-rewrite-quota: total "
                f"{supplied_total} is below the minimum of {_MIN_QUOTA} "
                "and no [REWRITE QUOTA EXEMPTION: ...] marker is present.\n"
                "WHY: every code-changing session must produce at least "
                f"{_MIN_QUOTA} improvements, OR provide deterministic "
                "evidence that further improvements in the touched area "
                "are not justified.\n"
                "UNBLOCK option A: produce more improvements until "
                f"total >= {_MIN_QUOTA}, update the marker, and re-run.\n"
                "UNBLOCK option B: create a JSON evidence file under "
                "docs/rewrite-evidence/<session-id>.json and add the "
                "[REWRITE QUOTA EXEMPTION: ...] marker referencing it.\n"
            )

        sub_failures = []
        for name, minimum, desc in _CATEGORIES:
            if values[name] < minimum:
                sub_failures.append(
                    f"{name}={values[name]} (need {minimum}): {desc}"
                )

        if sub_failures:
            return _fail(
                "FAIL check-rewrite-quota: per-category minimums "
                f"not met ({len(sub_failures)} of {_CATEGORY_COUNT} categories "
                "below their floor):\n"
                + "\n".join(f"  • {f}" for f in sub_failures)
                + "\n\nWHY: every code-changing session must produce "
                f"at least {_MIN_QUOTA} total improvements across "
                f"{_CATEGORY_COUNT} categories, each with a minimum of 15.\n"
                "Categories:\n"
                + _category_summary() + "\n"
            )

        if supplied_total >= _MIN_QUOTA:
            return 0
    else:
        return _fail(
            "FAIL check-rewrite-quota: code-changing commit but "
            "AGENT-HANDOFF.md is missing the rewrite count marker.\n"
            f"Expected format: {_marker_template()}\n\n"
            f"WHY: the Rewrite Quota rule requires {_MIN_QUOTA} "
            f"total improvements across {_CATEGORY_COUNT} categories (15 each):\n"
            + _category_summary()
            + "\n\nUNBLOCK: add the marker after counting each "
            "category, OR provide a [REWRITE QUOTA EXEMPTION: ...] "
            "marker with a JSON evidence file.\n"
        )


if __name__ == "__main__":
    sys.exit(main())
