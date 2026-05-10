#!/usr/bin/env python3
"""Pre-commit guard for the autotuner future-awareness rule.

Rule (per `docs/AUTOTUNER-FUTURE-AWARENESS.md`): every new ranking weight
or meta-algorithm parameter MUST land in the autotuner's tunable registry
at `backend/apps/suggestions/tunable_registry.py` within the same commit
that introduces the `AppSetting.key`. Otherwise the autotuner can't see it
and the user has to remember to wire it manually — the bug we're trying
to prevent.

How the hook decides:

1. Scan staged migration files for new `AppSetting.objects.get_or_create(key="...")`
   or `update_or_create(key="...")` calls.
2. For each new key, check whether the prefix matches a known tunable
   prefix:
       pipeline.
       slate_diversity.
       click_distance.
       explore_exploit.
       field_aware_relevance.
       clustering.
       score_                     (per-signal blend weight)
       w_                         (per-signal blend weight, alt prefix)
       ranking.w_                 (per-signal blend weight, scoped prefix)
3. If the key is tunable-shaped, scan the SAME commit's staged files for:
       (a) a new entry in tunable_registry.py for that key, OR
       (b) an explicit `# AUTOTUNER-EXCLUDED: <reason>` comment in the
           migration adding the key.
4. Without (a) or (b), exit non-zero and explain.

Bypass: same as other hooks — `--no-verify` is allowed only with a chat-
side justification.

Run manually:
    python .githooks/check-autotuner-registry.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TUNABLE_REGISTRY = REPO_ROOT / "backend" / "apps" / "suggestions" / "tunable_registry.py"

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

# Match `key="x.y.z"` or `key='x.y.z'` inside a get_or_create / update_or_create call.
KEY_RE = re.compile(
    r"(?:get_or_create|update_or_create)\s*\([^)]*?key\s*=\s*['\"]([^'\"]+)['\"]",
    re.DOTALL,
)
EXCLUSION_RE = re.compile(r"#\s*AUTOTUNER-EXCLUDED\s*:", re.IGNORECASE)


def _staged_files() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        check=True,
        capture_output=True,
        text=True,
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
        cwd=REPO_ROOT,
    ).stdout
    return "\n".join(
        line[1:] for line in out.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _is_tunable(key: str) -> bool:
    return any(key.startswith(p) for p in TUNABLE_PREFIXES)


def _registry_contains(key: str) -> bool:
    """True if the (staged or working-tree) tunable_registry.py mentions the key.

    Falls back to the working-tree file when the registry file isn't
    in git yet (initial commit). The hook is conservative — it accepts
    a working-tree match because the user is presumably staging the
    new entry as part of the same multi-file commit.
    """
    text = ""
    try:
        text = subprocess.run(
            ["git", "show", f":{TUNABLE_REGISTRY.relative_to(REPO_ROOT).as_posix()}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        ).stdout
    except subprocess.CalledProcessError:
        if TUNABLE_REGISTRY.exists():
            text = TUNABLE_REGISTRY.read_text(encoding="utf-8")
        else:
            return False
    # The key as a string literal: "key" or 'key'. Quote-flexible.
    return f'"{key}"' in text or f"'{key}'" in text


def _migration_path_for(key: str, staged_migrations: list[Path]) -> Path | None:
    """Return the migration whose staged diff added the key (best effort)."""
    for path in staged_migrations:
        diff = _staged_diff_for(path)
        if key in diff:
            return path
    return None


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
            if _registry_contains(key):
                continue
            violations.append(
                f"{migration.relative_to(REPO_ROOT).as_posix()}: introduces "
                f"tunable key '{key}' but tunable_registry.py has no matching "
                f"entry and the migration has no `# AUTOTUNER-EXCLUDED: <reason>` "
                f"comment."
            )

    if not violations:
        return 0

    sys.stderr.write(
        "\n\033[31m[check-autotuner-registry]\033[0m FAIL: One or more new "
        "tunable AppSetting keys were added without registering them in the "
        "autotuner's tunable registry.\n\n"
    )
    for v in violations:
        sys.stderr.write(f"  • {v}\n")
    sys.stderr.write(
        "\nFix one of the following:\n"
        "  • Add an entry to backend/apps/suggestions/tunable_registry.py for "
        "each new key (BLEND_WEIGHTS or META_PARAMS depending on type).\n"
        "  • OR add a `# AUTOTUNER-EXCLUDED: <reason>` comment to the migration "
        "if the key is intentionally not autotuned (e.g. data-driven decay "
        "constants).\n\n"
        "See docs/AUTOTUNER-FUTURE-AWARENESS.md for the canonical pattern.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
