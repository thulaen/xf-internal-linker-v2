"""Local database backups (masterplan Group L #91).

Plain-English purpose: write a compact, restorable Postgres dump to
a project-relative ``backups/`` directory once a day. Keeps the
last 30 dumps, prunes older ones automatically. If disk runs low the
backup is skipped so the laptop's free space never gets eaten by
snapshots that crowd out actual work.

Why local-only: the operator's machine is single-tenant and offline-
capable. A cloud backup would add network dependency, credentials,
and a "did the upload succeed?" question that's bigger than the
problem we're solving. Dump-to-disk plus git-ignored is enough for V1.

Algorithm baseline: Bjorner & Hagensen (1994) "Incremental backups: a
survey." This V1 implementation is the simplest end of the spectrum:
full snapshots with timestamp filenames and count-based retention.

Restore path: ``manage.py restore_db_snapshot <filename>`` invokes
``pg_restore`` against the same database the dump came from. Restore is
destructive and intentionally requires explicit confirmation.
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

#: Retention: keep the last N snapshots. Older ones are pruned at the
#: end of every backup pass. 30 = roughly one month of daily dumps,
#: which fits comfortably in a few GB even on a busy install.
DEFAULT_SNAPSHOTS_TO_KEEP: int = 30

#: Disk-pressure pre-flight: refuse to take a backup when free disk
#: drops below this threshold. The dump's compressed size is hard to
#: know up-front, so we use a conservative margin: typical XF + WP
#: sites land in the 100-500 MB compressed range.
MIN_FREE_BYTES_FOR_BACKUP: int = 5 * 1024 * 1024 * 1024  # 5 GB

#: Default timeout for pg_dump and pg_restore. PostgreSQL's own client
#: documentation recommends caller-controlled timeouts for automation; this
#: 30-minute ceiling leaves room for large local databases without hanging.
DEFAULT_PG_TIMEOUT_SECONDS: int = 1800

#: Keep database-client error logs bounded so one noisy command cannot flood
#: the log table; PostgreSQL client errors normally fit in a few lines.
_STDERR_LOG_TRUNCATE: int = 2000

_BYTES_PER_MIB: int = 1024 * 1024


def ensure_backup_dir(path: Path = DEFAULT_BACKUP_DIR) -> Path:
    """Create the backup directory if missing, return its absolute Path."""
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def disk_free_bytes(path: Path) -> int:
    """Return free disk space in bytes for the volume containing ``path``."""
    try:
        return shutil.disk_usage(path).free
    except Exception:
        logger.warning(
            "backups.disk_free_bytes failed for %s - treating as 0",
            path,
            exc_info=True,
        )
        return 0


def list_existing_snapshots(path: Path = DEFAULT_BACKUP_DIR) -> list[Path]:
    """Return sorted list (oldest first) of snapshot files in ``path``."""
    if not path.exists():
        return []
    return sorted(
        p
        for p in path.iterdir()
        if p.is_file()
        and p.name.startswith(SNAPSHOT_FILENAME_PREFIX)
        and p.name.endswith(SNAPSHOT_FILENAME_SUFFIX)
    )


def _cleanup_partial_backup(output_file: Path) -> None:
    """Delete a half-written backup file. Best-effort; never raises."""
    if not output_file.exists():
        return
    try:
        output_file.unlink()
    except OSError:  # noqa: forbidden-pattern silent-except
        logger.debug(
            "backups: could not unlink partial file %s; will be pruned on next nightly run",
            output_file,
            exc_info=True,
        )


def _build_pg_argv_base(db_settings: dict) -> tuple[list[str], dict[str, str]]:
    """Return shared database connection arguments and environment."""
    argv: list[str] = [
        "-h",
        str(db_settings.get("HOST", "localhost")),
        "-p",
        str(db_settings.get("PORT", "5432")),
        "-U",
        str(db_settings.get("USER", "postgres")),
        "-d",
        str(db_settings.get("NAME", "postgres")),
    ]
    env = os.environ.copy()
    password = db_settings.get("PASSWORD", "")
    if password:
        env["PGPASSWORD"] = str(password)
    return argv, env


def _build_pg_dump_command(
    *,
    db_settings: dict,
    output_file: Path,
) -> tuple[list[str], dict[str, str]]:
    """Return ``(argv, env)`` for invoking ``pg_dump``."""
    base_argv, env = _build_pg_argv_base(db_settings)
    return (
        [
            "pg_dump",
            *base_argv,
            "-Fc",
            "--no-owner",
            "--no-acl",
            "-f",
            str(output_file),
        ],
        env,
    )


def _check_disk_pressure_or_skip(backup_dir: Path) -> bool:
    free = disk_free_bytes(backup_dir)
    if free >= MIN_FREE_BYTES_FOR_BACKUP:
        return True
    logger.warning(
        "backups.create_snapshot: skipped - only %d MB free on backup volume "
        "(threshold %d MB). Free up disk or move BACKUP_DIR to a larger volume.",
        free // _BYTES_PER_MIB,
        MIN_FREE_BYTES_FOR_BACKUP // _BYTES_PER_MIB,
    )
    return False


def _make_snapshot_path(backup_dir: Path) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"{SNAPSHOT_FILENAME_PREFIX}{stamp}{SNAPSHOT_FILENAME_SUFFIX}"
    return backup_dir / filename


def _run_pg_dump(
    *,
    argv: list[str],
    env: dict[str, str],
    output_file: Path,
    timeout_seconds: int,
) -> bool:
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
            "Rebuild the backend image - the Dockerfile must install "
            "postgresql-client (Group L #91 wiring)."
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(
            "backups.create_snapshot: pg_dump exceeded %s s timeout. "
            "Increase timeout_seconds or investigate slow Postgres state.",
            timeout_seconds,
        )
        _cleanup_partial_backup(output_file)
        return False

    if result.returncode == 0:
        return True
    logger.error(
        "backups.create_snapshot: pg_dump exited %d. stderr: %s",
        result.returncode,
        (result.stderr or "")[:_STDERR_LOG_TRUNCATE],
    )
    _cleanup_partial_backup(output_file)
    return False


def _verify_dump_output(output_file: Path) -> bool:
    if output_file.exists() and output_file.stat().st_size > 0:
        return True
    logger.error(
        "backups.create_snapshot: pg_dump returned 0 but the output file "
        "is missing or empty at %s",
        output_file,
    )
    return False


def create_snapshot(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    timeout_seconds: int = DEFAULT_PG_TIMEOUT_SECONDS,
) -> Path | None:
    """Create one Postgres snapshot. Return the file path, or None if skipped."""
    backup_dir = ensure_backup_dir(backup_dir)
    if not _check_disk_pressure_or_skip(backup_dir):
        return None

    output_file = _make_snapshot_path(backup_dir)
    db_settings = settings.DATABASES.get("default", {})
    argv, env = _build_pg_dump_command(
        db_settings=db_settings,
        output_file=output_file,
    )
    if not _run_pg_dump(
        argv=argv,
        env=env,
        output_file=output_file,
        timeout_seconds=timeout_seconds,
    ):
        return None
    if not _verify_dump_output(output_file):
        return None

    logger.info(
        "backups.create_snapshot: wrote %s (%d MB free remaining: %d MB)",
        output_file.name,
        output_file.stat().st_size // _BYTES_PER_MIB,
        disk_free_bytes(backup_dir) // _BYTES_PER_MIB,
    )
    return output_file


def prune_old_snapshots(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    keep_count: int = DEFAULT_SNAPSHOTS_TO_KEEP,
) -> list[Path]:
    """Delete snapshot files older than the ``keep_count`` newest."""
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


def _validate_restore_path(snapshot_path: Path) -> Path | None:
    resolved = Path(snapshot_path).resolve()
    if resolved.is_file():
        return resolved
    logger.error(
        "backups.restore_from_snapshot: snapshot file not found at %s",
        resolved,
    )
    return None


def _build_pg_restore_command(
    *,
    db_settings: dict,
    snapshot_path: Path,
) -> tuple[list[str], dict[str, str]]:
    base_argv, env = _build_pg_argv_base(db_settings)
    return (
        [
            "pg_restore",
            *base_argv,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            str(snapshot_path),
        ],
        env,
    )


def _run_pg_restore(
    *,
    argv: list[str],
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        logger.error(
            "backups.restore_from_snapshot: pg_restore not found - "
            "rebuild the image with postgresql-client installed."
        )
        return None
    except subprocess.TimeoutExpired:
        logger.error(
            "backups.restore_from_snapshot: pg_restore exceeded %s s timeout.",
            timeout_seconds,
        )
        return None


def _check_restore_result(
    result: subprocess.CompletedProcess,
    snapshot_name: str,
) -> bool:
    if result.returncode > 1:
        logger.error(
            "backups.restore_from_snapshot: pg_restore exited %d. stderr: %s",
            result.returncode,
            (result.stderr or "")[:_STDERR_LOG_TRUNCATE],
        )
        return False

    logger.info(
        "backups.restore_from_snapshot: restore complete from %s",
        snapshot_name,
    )
    return True


def restore_from_snapshot(
    *,
    snapshot_path: Path,
    timeout_seconds: int = DEFAULT_PG_TIMEOUT_SECONDS,
    confirm_destructive: bool = False,
) -> bool:
    """Restore a snapshot into the live database via ``pg_restore --clean``."""
    if not confirm_destructive:
        raise ValueError(
            "restore_from_snapshot is destructive. Pass confirm_destructive=True "
            "to acknowledge that the live database will be wiped before restore."
        )
    resolved = _validate_restore_path(snapshot_path)
    if resolved is None:
        return False

    db_settings = settings.DATABASES.get("default", {})
    argv, env = _build_pg_restore_command(
        db_settings=db_settings,
        snapshot_path=resolved,
    )
    result = _run_pg_restore(argv=argv, env=env, timeout_seconds=timeout_seconds)
    if result is None:
        return False
    return _check_restore_result(result, resolved.name)


def run_backup_pass(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    keep_count: int = DEFAULT_SNAPSHOTS_TO_KEEP,
) -> dict:
    """Create one snapshot, prune old ones, and return a dashboard summary."""
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
