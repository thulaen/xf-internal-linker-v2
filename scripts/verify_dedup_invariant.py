#!/usr/bin/env python3
"""CI dedup auditor — calls the boot-time self-audit from a CLI.

Wraps ``apps.core.services.self_test_smoke.run_startup_smoke_tests()`` so
CI can fail a PR if any per-content artefact table doesn't satisfy the
NO-DUPLICATES.md invariant.

Usage from CI::

    python scripts/backend_manage.py shell -c "from apps.core.services.self_test_smoke import run_startup_smoke_tests; print(run_startup_smoke_tests())"
    # exit 0 = clean
    # exit 1 = at least one warning (with table list printed)

Or stand-alone via Django manage::

    python manage.py shell -c "
        import sys
        from apps.core.services.self_test_smoke import run_startup_smoke_tests
        warnings = run_startup_smoke_tests()
        if warnings:
            for w in warnings: print(w)
            sys.exit(1)
    "

The audit is the same code that runs on every backend boot — having it
also as a CI gate catches regressions before they reach production.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make ``backend/`` importable as the project root.
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")


def main() -> int:
    """Run the same smoke check the backend runs at boot.

    Returns 0 on a clean audit, 1 on any warning. The warning text
    comes verbatim from ``self_test_smoke`` so the operator sees the
    same message the dashboard shows.
    """
    try:
        import django

        django.setup()
    except Exception as exc:  # pragma: no cover — bootstrap-only
        print(f"[verify_dedup_invariant] Django setup failed: {exc}")
        return 2

    try:
        from apps.core.services.self_test_smoke import run_startup_smoke_tests
    except Exception as exc:  # pragma: no cover
        print(f"[verify_dedup_invariant] could not import smoke runner: {exc}")
        return 2

    warnings = run_startup_smoke_tests()
    if not warnings:
        print("[verify_dedup_invariant] No issues — every per-content artefact table satisfies NO-DUPLICATES.md.")
        return 0

    print("[verify_dedup_invariant] FAIL — the following tables violate the no-dups invariant:\n")
    for warning in warnings:
        print(f"  • {warning}")
    print(
        "\nFix each violation per NO-DUPLICATES.md (add `content_hash` / "
        "`signal_version` / unique constraint / supersede + retention) OR add the "
        "model to ARTIFACT_RULES in apps/core/services/self_test_smoke.py with the "
        "right declaration."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
