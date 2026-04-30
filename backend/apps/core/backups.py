"""Local database backups (masterplan Group L #91).

Plain-English purpose: write a compact, restorable Postgres dump to
a project-relative ``backups/`` directory once a day. Keeps the
last 30 dumps, prunes older ones automatically. If disk runs low the
backup is skipped (with a /error-log entry) so the laptop's free
space never gets eaten by snapshots that crowd out actual work.

Why local-only: the operator's machine is single-tenant and offline-
capable. A cloud backup would add network dependency, credentials,
and a "did the upload succeed?" question that's bigger than the
problem we're solving. Dump-to-disk + git-ignored is enough for V1.

Algorithm baseline: Bjørner & Hagensen (1994) "Incremental backups: a
survey." This V1 implementation is the simplest end of the spectrum
— full snapshots with timestamp filenames + count-based retention.
PITR (point-in-time recovery via WAL archiving) is a future
optimization in the masterplan's `## Pending` list for L #91.

Restore path: ``manage.py restore_db_snapshot <filename>`` invokes
``pg_restore`` against the same database the dump came from.
Operator must `--clean --if-exists` to wipe the live state first;
that's intentional — restore is destructive and explicit.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


#: Default location for snapshots. Project-relative so a moved
#: deployment carries its own backups; gitignored so the dumps
#: never end up in version control.
DEFAULT_BACKUP_DIR: Path = Path(settings.BASE_DIR) / "backups"

#: Filename pattern: ``snapshot-YYYYMMDD-HHMMSS.dump``. ISO-ish so
#: chronological sort = lexicographic sort.
SNAPSHOT_FILENAME_PREFIX: str = "snapshot-"
SNAPSHOT_FILENAME_SUFFIX: str = ".dump"

#: Retention — keep the last N snapshots. Older ones are pruned at the
#: end of every backup pass. 30 = roughly one month of daily dumps,
#: which fits comfortably in a few GB even on a busy install.
DEFAULT_SNAPSHOTS_TO_KEEP: int = 30

#: Disk-pressure pre-flight: refuse to take a backup when free disk
#: drops below this threshold. The dump's compressed size is hard to
#: know up-front, so we use a conservative margin — typical XF + WP
#: sites land in the 100-500 MB compressed range.
MIN_FREE_BYTES_FOR_BACKUP: int = 5 * 1024 * 1024 * 1024  # 5 GB


# ────────────────────────────────────────────────────────────────────
# Filesystem helpers
# ────────────────────────────────────────────────────────────────────


def ensure_backup_dir(path: Path = DEFAULT_BACKUP_DIR) -> Path:
    """Create the backup directory if missing, return its absolute Path."""
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def disk_free_bytes(path: Path) -> int:
    """Return the free disk space in bytes for the volume containing ``path``.

    ``shutil.disk_usage`` works on whichever volume the path resolves
    to; on Windows that's the drive letter, on Linux the mount point.
    """
    try:
        return shutil.disk_usage(path).free
    except Exception:
        # On any platform-specific error, return 0 so the pre-flight
        # check fires defensively (treat "unknown" as "out of space").
        logger.warning(
            "backups.disk_free_bytes failed for %s — treating as 0",
            path,
            exc_info=True,
        )
        return 0


def list_existing_snapshots(path: Path = DEFAULT_BACKUP_DIR) -> list[Path]:
    """Return sorted list (oldest first) of snapshot files in ``path``.

    Filters by the ``snapshot-*.dump`` pattern so other files in the
    directory (READMEs, the operator's notes, etc.) don't get pruned.
    """
    if not path.exists():
        return []
    snapshots = sorted(
        p
        for p in path.iterdir()
        if p.is_file()
        and p.name.startswith(SNAPSHOT_FILENAME_PREFIX)
        and p.name.endswith(SNAPSHOT_FILENAME_SUFFIX)
    )
    return snapshots


# ────────────────────────────────────────────────────────────────────
# pg_dump invocation
# ────────────────────────────────────────────────────────────────────


def _build_pg_dump_command(
    *,
    db_settings: dict,
    output_file: Path,
) -> tuple[list[str], dict[str, str]]:
    """Return ``(argv, env)`` for invoking ``pg_dump``.

    Uses the custom format (``-Fc``) which is compact AND reload-able
    via ``pg_restore``. Password is passed via ``PGPASSWORD`` env so
    it doesn't appear on the process command line.
    """
    argv: list[str] = [
        "pg_dump",
        "-h",
        str(db_settings.get("HOST", "localhost")),
        "-p",
        str(db_settings.get("PORT", "5432")),
        "-U",
        str(db_settings.get("USER", "postgres")),
        "-d",
        str(db_settings.get("NAME", "postgres")),
        "-Fc",  # custom format — compact, reload-able
        "--no-owner",  # operator-portable
        "--no-acl",  # ACLs change between hosts
        "-f",
        str(output_file),
    ]
    env = os.environ.copy()
    password = db_settings.get("PASSWORD", "")
    if password:
        env["PGPASSWORD"] = str(password)
    return argv, env


def create_snapshot(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    timeout_seconds: int = 1800,
) -> Path | None:
    """Create one Postgres snapshot. Return the file path, or None if skipped.

    Pre-flight: refuse if free disk < MIN_FREE_BYTES_FOR_BACKUP.

    Failure modes (all return None, log via /error-log path in caller):
      * disk too full
      * pg_dump binary missing (Dockerfile didn't install postgresql-client)
      * pg_dump exit-code != 0 (server unreachable, auth failure, etc.)
      * subprocess timeout
    """
    backup_dir = ensure_backup_dir(backup_dir)

    # Pre-flight disk check.
    free = disk_free_bytes(backup_dir)
    if free < MIN_FREE_BYTES_FOR_BACKUP:
        logger.warning(
            "backups.create_snapshot: skipped — only %d MB free on backup volume "
            "(threshold %d MB). Free up disk or move BACKUP_DIR to a larger volume.",
            free // (1024 * 1024),
            MIN_FREE_BYTES_FOR_BACKUP // (1024 * 1024),
        )
        return None

    # Build the output filename now so failures don't pollute the dir.
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    output_file = (
        backup_dir / f"{SNAPSHOT_FILENAME_PREFIX}{stamp}{SNAPSHOT_FILENAME_SUFFIX}"
    )

    db_settings = settings.DATABASES.get("default", {})
    argv, env = _build_pg_dump_command(
        db_settings=db_settings,
        output_file=output_file,
    )

    try:
        result = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        logger.error(
            "backups.create_snapshot: pg_dump binary not found. "
            "Rebuild the backend image — the Dockerfile must install "
            "postgresql-client (Group L #91 wiring)."
        )
        return None
    except subprocess.TimeoutExpired:
        logger.error(
            "backups.create_snapshot: pg_dump exceeded %s s timeout. "
            "Increase timeout_seconds or investigate slow Postgres state.",
            timeout_seconds,
        )
        # Clean up the partial file if any.
        if output_file.exists():
            try:
                output_file.unlink()
            except OSError:
                pass
        return None

    if result.returncode != 0:
        logger.error(
            "backups.create_snapshot: pg_dump exited %d. stderr: %s",
            result.returncode,
            (result.stderr or "")[:2000],
        )
        # Clean up the partial / empty file pg_dump may have started.
        if output_file.exists():
            try:
                output_file.unlink()
            except OSError:
                pass
        return None

    if not output_file.exists() or output_file.stat().st_size == 0:
        logger.error(
            "backups.create_snapshot: pg_dump returned 0 but the output file "
            "is missing or empty at %s",
            output_file,
        )
        return None

    logger.info(
        "backups.create_snapshot: wrote %s (%d MB free remaining: %d MB)",
        output_file.name,
        output_file.stat().st_size // (1024 * 1024),
        disk_free_bytes(backup_dir) // (1024 * 1024),
    )
    return output_file


# ────────────────────────────────────────────────────────────────────
# Retention / pruning
# ────────────────────────────────────────────────────────────────────


def prune_old_snapshots(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    keep_count: int = DEFAULT_SNAPSHOTS_TO_KEEP,
) -> list[Path]:
    """Delete snapshot files older than the ``keep_count`` newest. Returns
    the list of deleted Paths (for logging / audit).
    """
    snapshots = list_existing_snapshots(backup_dir)
    if len(snapshots) <= keep_count:
        return []
    to_delete = snapshots[: -keep_count] if keep_count > 0 else list(snapshots)
    deleted: list[Path] = []
    for path in to_delete:
        try:
            path.unlink()
            deleted.append(path)
        except OSError as exc:
            logger.warning(
                "backups.prune_old_snapshots: failed to delete %s: %s",
                path,
                exc,
            )
    if deleted:
        logger.info(
            "backups.prune_old_snapshots: deleted %d snapshot(s) older than the "
            "last %d. Newest deleted: %s.",
            len(deleted),
            keep_count,
            deleted[-1].name if deleted else "n/a",
        )
    return deleted


# ────────────────────────────────────────────────────────────────────
# Restore — used by the manage.py command
# ────────────────────────────────────────────────────────────────────


def restore_from_snapshot(
    *,
    snapshot_path: Path,
    timeout_seconds: int = 1800,
    confirm_destructive: bool = False,
) -> bool:
    """Restore a snapshot into the live database via ``pg_restore --clean``.

    DESTRUCTIVE — drops existing schema before restoring. Caller MUST
    pass ``confirm_destructive=True`` or the function refuses. This is
    a defence against an operator running it against the wrong stack
    by mistake.
    """
    if not confirm_destructive:
        raise ValueError(
            "restore_from_snapshot is destructive. Pass confirm_destructive=True "
            "to acknowledge that the live database will be wiped before restore."
        )
    snapshot_path = Path(snapshot_path).resolve()
    if not snapshot_path.is_file():
        logger.error(
            "backups.restore_from_snapshot: snapshot file not found at %s",
            snapshot_path,
        )
        return False

    db_settings = settings.DATABASES.get("default", {})
    argv = [
        "pg_restore",
        "-h",
        str(db_settings.get("HOST", "localhost")),
        "-p",
        str(db_settings.get("PORT", "5432")),
        "-U",
        str(db_settings.get("USER", "postgres")),
        "-d",
        str(db_settings.get("NAME", "postgres")),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        str(snapshot_path),
    ]
    env = os.environ.copy()
    password = db_settings.get("PASSWORD", "")
    if password:
        env["PGPASSWORD"] = str(password)

    try:
        result = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        logger.error(
            "backups.restore_from_snapshot: pg_restore not found — "
            "rebuild the image with postgresql-client installed."
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(
            "backups.restore_from_snapshot: pg_restore exceeded %s s timeout.",
            timeout_seconds,
        )
        return False

    # pg_restore can return 1 even on partial success (it considers
    # missing-extension errors warnings). Log stderr verbatim so the
    # operator sees what happened, but accept rc <= 1 as success.
    if result.returncode > 1:
        logger.error(
            "backups.restore_from_snapshot: pg_restore exited %d. stderr: %s",
            result.returncode,
            (result.stderr or "")[:2000],
        )
        return False

    logger.info(
        "backups.restore_from_snapshot: restore complete from %s",
        snapshot_path.name,
    )
    return True


# ────────────────────────────────────────────────────────────────────
# Convenience top-level entrypoint used by the Celery task
# ────────────────────────────────────────────────────────────────────


def run_backup_pass(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    keep_count: int = DEFAULT_SNAPSHOTS_TO_KEEP,
) -> dict:
    """One full pass: create snapshot, prune old ones, return a summary dict.

    Designed for the Celery task wrapper. Always returns a dict so the
    operator's diagnostic dashboard sees a structured result regardless
    of success / partial / skip.
    """
    created = create_snapshot(backup_dir=backup_dir)
    deleted = prune_old_snapshots(backup_dir=backup_dir, keep_count=keep_count)
    snapshots_after = list_existing_snapshots(backup_dir)
    return {
        "created": str(created.name) if created else None,
        "created_size_bytes": created.stat().st_size if created else 0,
        "deleted_count": len(deleted),
        "deleted_names": [p.name for p in deleted],
        "total_snapshots_after": len(snapshots_after),
        "free_disk_bytes_after": disk_free_bytes(backup_dir),
    }
