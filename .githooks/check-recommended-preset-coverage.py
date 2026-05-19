#!/usr/bin/env python3
"""Pre-commit guard for the Recommended-preset coverage rule.

Rule (per `docs/AUTOTUNER-FUTURE-AWARENESS.md` and `docs/RANKING-GATES.md`
A10): every new tunable AppSetting key MUST also be added to the
Recommended preset within the same commit. Otherwise existing installs
never see the new default when they load the preset, and new defaults
silently diverge from what the autotuner expects.

How the hook decides:

1. Reuse the same prefix list and key-extraction logic as
   check-autotuner-registry.py — this hook fires on the same set of new
   tunable keys.
2. For each new tunable key, scan the SAME commit for at least one of:
       (a) a new entry in
           backend/apps/suggestions/recommended_weights.py
           (i.e. a line of the form `"<key>": "<value>"` added in the
           staged diff), OR
       (b) a `WeightPreset.objects.filter(name='Recommended', is_system=True)`
           upsert in any staged migration touching the same key, OR
       (c) the same `# AUTOTUNER-EXCLUDED: <reason>` comment as the
           autotuner-registry hook (excluded from the autotuner is also
           excluded from preset-coverage enforcement).
3. Without (a), (b), or (c), exit non-zero and explain.

Run manually:
    python .githooks/check-recommended-preset-coverage.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECOMMENDED_FILE = (
    REPO_ROOT / "backend" / "apps" / "suggestions" / "recommended_weights.py"
)

TUNABLE_PREFIXES = (
    "pipeline.",
    "slate_diversity.",
    "click_distance.",
    "explore_exploit.",
    "field_aware_relevance.",
    "clustering.",
    "score_",
    "w_",
    "ranking.w_",
)

KEY_RE = re.compile(
    r"(?:get_or_create|update_or_create)\s*\([^)]*?key\s*=\s*['\"]([^'\"]+)['\"]",
    re.DOTALL,
)
EXCLUSION_RE = re.compile(r"#\s*AUTOTUNER-EXCLUDED\s*:", re.IGNORECASE)
WEIGHTPRESET_UPSERT_RE = re.compile(
    r"WeightPreset\.objects\.[^(]*\(.*?name\s*=\s*['\"]Recommended['\"]",
    re.DOTALL,
)


def _staged_files() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        check=True,
        capture_output=True,
        text=True,
            encoding="utf-8",
            errors="replace",
        cwd=REPO_ROOT,
    ).stdout.splitlines()
    return [REPO_ROOT / p for p in out if p]


def _staged_diff_for(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).as_posix()
    out = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--", rel],
        check=False,
        capture_output=True,
        text=True,
            encoding="utf-8",
            errors="replace",
        cwd=REPO_ROOT,
    ).stdout
    return "\n".join(
        line[1:] for line in out.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _is_tunable(key: str) -> bool:
    return any(key.startswith(p) for p in TUNABLE_PREFIXES)


def _recommended_diff_contains_key(key: str) -> bool:
    """True if the staged diff of recommended_weights.py introduces this key."""
    if not RECOMMENDED_FILE.exists():
        return False
    diff = _staged_diff_for(RECOMMENDED_FILE)
    return f'"{key}"' in diff or f"'{key}'" in diff


def _migration_has_preset_upsert(migration: Path, key: str) -> bool:
    diff = _staged_diff_for(migration)
    if not WEIGHTPRESET_UPSERT_RE.search(diff):
        return False
    return key in diff


def main() -> int:
    staged = _staged_files()
    migrations = [
        p for p in staged
        if p.suffix == ".py" and "/migrations/" in p.as_posix()
    ]
    if not migrations:
        return 0

    violations: list[str] = []
    for migration in migrations:
        if not migration.exists():
            continue
        diff = _staged_diff_for(migration)
        for match in KEY_RE.finditer(diff):
            key = match.group(1)
            if not _is_tunable(key):
                continue
            if EXCLUSION_RE.search(diff):
                continue
            if _recommended_diff_contains_key(key):
                continue
            if _migration_has_preset_upsert(migration, key):
                continue
            violations.append(
                f"{migration.relative_to(REPO_ROOT).as_posix()}: introduces "
                f"tunable key '{key}' but recommended_weights.py was not "
                f"updated and the migration has no WeightPreset(name='Recommended') "
                f"upsert."
            )

    if not violations:
        return 0

    sys.stderr.write(
        "\n\033[31m[check-recommended-preset-coverage]\033[0m FAIL: One or more "
        "new tunable AppSetting keys were added without ensuring the Recommended "
        "preset will pick them up.\n\n"
    )
    for v in violations:
        sys.stderr.write(f"  • {v}\n")
    sys.stderr.write(
        "\nFix one of the following:\n"
        "  • Add an entry for each new key in "
        "backend/apps/suggestions/recommended_weights.py "
        "(RECOMMENDED_PRESET_WEIGHTS dict).\n"
        "  • OR add a `WeightPreset.objects.filter(name='Recommended', "
        "is_system=True)` upsert that includes the new key in the same "
        "migration.\n"
        "  • OR add `# AUTOTUNER-EXCLUDED: <reason>` to the migration if "
        "the key intentionally lives outside the Recommended preset.\n\n"
        "See docs/AUTOTUNER-FUTURE-AWARENESS.md for the canonical pattern.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
