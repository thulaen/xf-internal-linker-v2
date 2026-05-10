#!/usr/bin/env python3
"""Pre-commit linter — flag design-pattern regressions in Angular templates.

Today (2026-05-10) the rule it enforces:

   The "Status: Active / Off" form-field pattern for ENABLE/DISABLE
   toggles is forbidden outside filter contexts. Use a header-level
   `<mat-slide-toggle>` instead, per `frontend/DESIGN-PATTERNS.md` §13.

Why a hook: 13 cards in `settings.component.html` got the legacy pattern
before the canonical card anatomy shipped. A migration via one-shot
transformer cleaned them all up. Without enforcement, the pattern WILL
creep back — the next agent doing a cards refactor without reading
DESIGN-PATTERNS.md will reach for the old `<mat-form-field><mat-label>
Status</mat-label><mat-select>...<mat-option>Active</mat-option>...`
shape because Angular Material's documentation shows it as a normal
form-field example.

What this hook DOES NOT block:

   - Filter dropdowns labelled `Status` whose options are NOT
     `Active`/`Off`/`Enabled`/`Disabled`. Filters use `Status: All /
     Pending / Reviewed / Approved / Rejected / etc.` — those keep
     being form fields. The hook only fires on the binary-toggle shape.
   - Cards whose title already declares an `i18n` attribute (legacy
     i18n pass) — those are exempt to avoid blocking the i18n rollout.

Bypass: add `<!-- noqa: design-pattern -->` directly above the offending
form field if there's a genuine reason to keep the legacy shape.

Exit codes:
    0 — staged template files clean (or none staged)
    1 — at least one staged template file violates the rule
    2 — linter itself failed (e.g. unparseable template)
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Files exempt — filters that legitimately use a Status select.
EXEMPT_FILES = (
    re.compile(r"frontend/src/app/error-log/", re.IGNORECASE),
    re.compile(r"frontend/src/app/alerts/", re.IGNORECASE),
    re.compile(r"frontend/src/app/audit/", re.IGNORECASE),
    re.compile(r"frontend/src/app/jobs/", re.IGNORECASE),
)

# Match the legacy "Status: Active/Off" pattern. The two `Active|Off|
# Enabled|Disabled` checks are what distinguishes a TOGGLE from a true
# multi-state filter. Using DOTALL so we can match across line breaks.
LEGACY_STATUS_TOGGLE_RE = re.compile(
    r"<mat-form-field[^>]*>\s*"
    r"<mat-label>\s*Status\s*</mat-label>\s*"
    r"<mat-select[^>]*>\s*"
    r"<mat-option\s+\[value\]=\"true\">\s*(?:Active|Enabled|On)\s*</mat-option>\s*"
    r"<mat-option\s+\[value\]=\"false\">\s*(?:Off|Disabled)\s*</mat-option>\s*"
    r"</mat-select>",
    re.IGNORECASE | re.DOTALL,
)

NOQA_RE = re.compile(r"<!--\s*noqa:\s*design-pattern\s*-->", re.IGNORECASE)


@dataclass
class Violation:
    path: Path
    lineno: int


def _staged_template_paths(args: list[str]) -> list[Path]:
    """Return staged Angular template paths to check."""
    if args:
        candidates = [Path(a) for a in args]
    else:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        ).stdout.splitlines()
        candidates = [Path(p) for p in out]
    return [p for p in candidates if p.suffix == ".html" and p.as_posix().startswith("frontend/")]


def _is_exempt(path: Path) -> bool:
    posix = path.as_posix()
    return any(rx.search(posix) for rx in EXEMPT_FILES)


def _scan_file(path: Path) -> list[Violation]:
    """Return violations in *path* — empty list when clean."""
    if _is_exempt(path):
        return []
    full = REPO_ROOT / path if not path.is_absolute() else path
    if not full.exists():
        return []
    try:
        source = full.read_text(encoding="utf-8")
    except OSError:
        return []
    violations: list[Violation] = []
    for match in LEGACY_STATUS_TOGGLE_RE.finditer(source):
        # Anchor lineno on the start of the match.
        lineno = source.count("\n", 0, match.start()) + 1
        # Walk back up to 3 lines looking for a noqa marker.
        upstream = "\n".join(source.splitlines()[max(0, lineno - 4):lineno])
        if NOQA_RE.search(upstream):
            continue
        violations.append(Violation(path=path, lineno=lineno))
    return violations


def main(argv: list[str]) -> int:
    paths = _staged_template_paths(argv[1:])
    if not paths:
        return 0

    all_violations: list[Violation] = []
    for path in paths:
        all_violations.extend(_scan_file(path))

    if not all_violations:
        return 0

    print(
        "\n[check-design-patterns] FAIL: staged template(s) use the "
        "legacy 'Status: Active/Off' form-field pattern for an "
        "enable/disable toggle. Promote to a header-level "
        "<mat-slide-toggle> per frontend/DESIGN-PATTERNS.md §13.\n"
    )
    for v in all_violations:
        print(f"  {v.path}:{v.lineno}")
    print(
        "\nFix shape:\n"
        "  - Remove the <mat-form-field> with <mat-label>Status</mat-label>\n"
        "    + Active/Off mat-select.\n"
        "  - Add a <div class=\"card-title-actions\"> inside the\n"
        "    <mat-card-header> with a <mat-slide-toggle [(ngModel)]=\"<feature>.enabled\">.\n"
        "  - Bind the toggle to the SAME `<feature>.enabled` model the\n"
        "    select bound to — no backend change needed.\n"
        "  - See frontend/DESIGN-PATTERNS.md §13 for the canonical structure.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
