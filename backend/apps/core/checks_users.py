"""Startup safety check — warn loudly if the auth_user table is empty.

Plain-English: if the database has zero users AND the project's
``backups/`` directory already contains snapshots, that combination
is suspicious — it almost always means a Docker rebuild lost the
``pgdata`` volume. The check fires a Django ``Warning`` (code
``core.W001``) which surfaces in ``manage.py check`` output and in
backend startup logs, pointing the operator at the recovery doc.

Read-only by design: never writes to the database, never touches
passwords, never auto-creates users. The recovery path lives in
``docs/SAFE-DOCKER-REBUILD.md``.
"""

from __future__ import annotations

from pathlib import Path

from django.core.checks import Tags, Warning, register


def _has_snapshots() -> bool:
    """Return True if the project ``backups/`` directory contains any
    pg_dump snapshots. False otherwise.

    We import the live default location from ``apps.core.backups`` so
    the check stays in lock-step with the snapshot writer if the path
    ever moves.
    """
    try:
        from apps.core.backups import (
            DEFAULT_BACKUP_DIR,
            SNAPSHOT_FILENAME_PREFIX,
            SNAPSHOT_FILENAME_SUFFIX,
        )
    except Exception:  # noqa: BLE001
        # Startup checks must not crash boot before Django settings are ready.
        return False

    backup_dir: Path = DEFAULT_BACKUP_DIR
    if not backup_dir.exists():
        return False
    for entry in backup_dir.iterdir():
        if (
            entry.is_file()
            and entry.name.startswith(SNAPSHOT_FILENAME_PREFIX)
            and entry.name.endswith(SNAPSHOT_FILENAME_SUFFIX)
        ):
            return True
    return False


def _is_test_run() -> bool:
    """Return True when Django is running its test runner.

    Tests start with an empty user table by design; firing W001 every
    test run would just be noise.
    """
    import sys

    if any(arg == "test" for arg in sys.argv[1:3]):
        return True
    try:
        from django.db import connections

        db_name = connections["default"].settings_dict.get("NAME") or ""
        if isinstance(db_name, str) and db_name.startswith("test_"):
            return True
    except Exception:  # noqa: BLE001
        # Missing database wiring means this is not provably a test run.
        return False
    return False


@register(Tags.database)
def warn_if_users_lost(app_configs, **kwargs):
    """Fire core.W001 when auth_user is empty but backups/ has snapshots."""
    # Skip during test runs: every test DB starts empty, the host's
    # backups/ directory is full of snapshots, so this would fire on
    # every test run. The condition we care about (real DB, real
    # snapshots, zero users) only applies to live boots.
    if _is_test_run():
        return []

    # Skip during fresh checkouts where the system has never been used.
    if not _has_snapshots():
        return []

    # Reading the user model requires the apps to be ready. If something
    # imports this check before then, return silently — the next normal
    # invocation will catch the condition.
    try:
        from django.contrib.auth import get_user_model

        if get_user_model().objects.exists():
            return []
    except Exception:  # noqa: BLE001
        # Apps or the database may be mid-startup; the next check will retry.
        return []

    return [
        Warning(
            "auth_user is empty, but backups/ already contains snapshots — "
            "this almost always means a Docker rebuild lost the pgdata volume.",
            hint=(
                "Recovery: see docs/SAFE-DOCKER-REBUILD.md. "
                "Quick path: python scripts/backend_manage.py "
                "restore_db_snapshot --latest --confirm. "
                "Future rebuilds: use scripts/safe-rebuild.ps1."
            ),
            id="core.W001",
        )
    ]
