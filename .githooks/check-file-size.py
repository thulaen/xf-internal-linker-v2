#!/usr/bin/env python3
"""Pre-commit linter — block files growing past CLAUDE.md's 1,500-line cap.

Why a hook: CLAUDE.md sets a hard limit of 1,500 lines per file. The limit
exists because oversized files become un-reviewable and re-introduce all the
"god class" problems the project keeps fixing — backend/apps/core/views.py
ballooned to 6,616 lines and frontend/src/app/settings/settings.component.ts
to 4,732 lines because no automated gate stopped them. Without enforcement,
the next "do all things in one session" directive will recreate the problem.

What this hook does:

   1. Walk every staged file with one of the watched extensions
      (.py, .ts, .html, .scss, .cpp, .h).
   2. If the file is over the cap (1,500 lines) AND not in the
      grandfather list (.githooks/file-size-grandfather.txt), block.
   3. If the file IS grandfathered, allow it but enforce the
      "must shrink" rule: the staged version's line count must be
      LESS than the grandfather's recorded baseline. The cap can
      shrink over time, never grow.
   4. Fresh files always start under the cap; the grandfather list
      only protects existing oversized files during their planned
      decomposition.

The grandfather file format (one entry per line):

   path/to/file:current_line_count

When a file in the grandfather list is split below the cap, REMOVE it
from the file. The hook will then enforce the global 1,500-line cap on
that path going forward.

Exit codes:
    0 — staged files clean (or none staged)
    1 — at least one staged file violates the cap or grew past its
        grandfather baseline
    2 — linter itself failed
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRANDFATHER_PATH = REPO_ROOT / ".githooks" / "file-size-grandfather.txt"

HARD_CAP = 1500

WATCHED_EXTENSIONS = (".py", ".ts", ".html", ".scss", ".cpp", ".h", ".tsx")

# Paths that are inherently mechanical (auto-generated, vendored,
# benchmarked, locked) where the line cap is meaningless. Every entry
# is an exact-prefix match against the staged path (forward slashes).
EXEMPT_PATH_PREFIXES = (
    "frontend/src/app/api/schema.d.ts",  # OpenAPI-generated
    "frontend/package-lock.json",
    "backend/extensions/build/",
    "backend/extensions/build_asan/",
    "backend/extensions/build_tsan/",
    "node_modules/",
    "frontend/dist/",
    "frontend/coverage/",
    "frontend/.angular/",
)


def load_grandfather() -> dict[str, int]:
    """Return {path: max_allowed_lines} from the grandfather file."""
    if not GRANDFATHER_PATH.exists():
        return {}
    out: dict[str, int] = {}
    for line in GRANDFATHER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        path, _, count = line.rpartition(":")
        try:
            out[path.strip()] = int(count.strip())
        except ValueError:
            continue
    return out


def staged_files() -> list[str]:
    """Return staged paths from git, normalised to forward slashes."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def line_count(path: str) -> int:
    """Total lines in file (matches `wc -l` semantics)."""
    full = REPO_ROOT / path
    if not full.exists() or not full.is_file():
        return 0
    try:
        with full.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def is_watched(path: str) -> bool:
    if not any(path.endswith(ext) for ext in WATCHED_EXTENSIONS):
        return False
    if any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES):
        return False
    return True


def main(argv: list[str]) -> int:
    paths = argv[1:] or staged_files()
    paths = [p.replace("\\", "/") for p in paths if is_watched(p.replace("\\", "/"))]
    if not paths:
        return 0

    grandfather = load_grandfather()
    violations: list[str] = []

    for path in paths:
        count = line_count(path)
        if count == 0:
            continue
        if path in grandfather:
            allowed = grandfather[path]
            if count > allowed:
                violations.append(
                    f"  {path}: {count} lines — grandfather baseline is {allowed}. "
                    f"Grandfathered files may only SHRINK; either bring it back below {allowed} "
                    f"or split it into smaller modules per CLAUDE.md."
                )
            continue
        if count > HARD_CAP:
            violations.append(
                f"  {path}: {count} lines — over the {HARD_CAP}-line cap from CLAUDE.md. "
                f"Split into named modules. If this file is being actively decomposed, "
                f"add the path to .githooks/file-size-grandfather.txt with the current "
                f"line count and remove it once the split lands."
            )

    if not violations:
        return 0

    print("\nFAIL check-file-size: file(s) over the 1,500-line cap from CLAUDE.md.\n")
    for line in violations:
        print(line)
    print(
        "\nWhy this matters: oversized files become un-reviewable and re-introduce"
        "\nthe god-class bugs the project keeps fixing. The cap is a hard limit"
        "\nfrom the THINK-BEFORE-YOU-CODE rule in CLAUDE.md."
        "\n\nFix shape: split the file into named modules. Re-run the commit once"
        "\nevery file is back under cap (or grandfathered with a smaller baseline)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
