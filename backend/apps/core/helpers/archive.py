"""``HelperArchive`` — heavy-data storage abstraction with helper-PC offload.

Pattern: a Celery task that needs to write a large blob (model checkpoint,
crawler raw HTML cache, OPQ codebook backup, RotatE training output)
asks ``HelperArchive`` for a Path. The archive routes the write to the
helper PC's SMB / NFS / local share when one is connected and online;
otherwise it falls back to the project-relative ``media/helper_archive/``
so dev still works.

Plain-English: instead of every feature inventing its own "where do I
put a 300 MB file" answer, ``HelperArchive`` does it for them. When a
second PC is plugged in, big files automatically land there. When no
helper exists, files stay local. Either way the calling code is the same.

Storage discipline:
    * NO new tables. Per-archive metadata (file path, size, written-at,
      retention TTL) is one AppSetting row per file, keyed by
      ``helper_archive.<archive_name>.<file_id>``.
    * Per-archive retention is configurable (defaults: 30 days for
      checkpoints, 7 days for raw HTML, 90 days for backups).
    * The existing ``nightly_data_retention`` task (Codex Slice 5,
      apps/pipeline/tasks.py) prunes expired archive files on its
      regular schedule — extends naturally; no new beat task needed.

Citations: pattern derived from S3-style object-storage abstraction +
Django's ``default_storage`` indirection.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


# Per-archive default retention (days). Override per archive at write
# time via ``HelperArchive(...).allocate(retention_days=N)``.
_DEFAULT_RETENTIONS: dict[str, int] = {
    "rotate_checkpoints": 30,
    "opq_codebooks": 90,
    "crawler_raw_html": 7,
    "postgres_backups": 90,
    "embedding_comparison_runs": 30,
    "deberta_finetune_state": 30,
}

# Local fallback root when no helper is connected.
LOCAL_FALLBACK_ROOT: Path = Path("media") / "helper_archive"


@dataclass(frozen=True, slots=True)
class AllocatedFile:
    """Concrete handle returned by ``allocate()``."""

    path: Path
    archive_name: str
    file_id: str
    is_helper_backed: bool
    retention_days: int


class HelperArchive:
    """Per-archive write surface. Construct once, allocate many.

    Example:

        from apps.core.helpers import HelperArchive

        archive = HelperArchive("rotate_checkpoints")
        handle = archive.allocate(size_bytes=300_000_000)
        with handle.path.open("wb") as f:
            f.write(checkpoint_bytes)

    The Path may live on a helper SMB mount (e.g.
    ``/mnt/xf-helper-archive/rotate_checkpoints/<id>.pt``) or on the
    main PC (e.g. ``media/helper_archive/rotate_checkpoints/<id>.pt``).
    Reads work the same way — `archive.read_path(file_id)` returns the
    Path the writer used, regardless of which node hosts it.
    """

    # Where the helper SMB share is mounted on the main PC. The
    # operator configures this at helper-enrollment time; defaults to
    # ``/mnt/xf-helper-archive`` (Linux) or ``H:\xf-helper-archive``
    # (Windows). Read from AppSetting at construction time so a runtime
    # mount-point change picks up without process restart.
    _APP_SETTING_MOUNT_POINT: ClassVar[str] = "helper_archive.mount_point"

    def __init__(self, archive_name: str) -> None:
        if not archive_name or "/" in archive_name or "\\" in archive_name:
            raise ValueError(
                "archive_name must be a simple identifier (no slashes)"
            )
        self.archive_name = archive_name

    def _resolve_root(self) -> tuple[Path, bool]:
        """Return ``(root, is_helper_backed)``.

        Picks the first working root in this order:
            1. Operator-configured ``helper_archive.mount_point`` if it
               exists and is writable.
            2. The platform default ``/mnt/xf-helper-archive`` (Linux)
               / ``H:\\xf-helper-archive`` (Windows) if writable.
            3. Local fallback ``media/helper_archive/``.
        """
        candidates: list[Path] = []
        try:
            from apps.core.models import AppSetting

            row = AppSetting.objects.filter(
                key=self._APP_SETTING_MOUNT_POINT
            ).first()
            if row and row.value:
                candidates.append(Path(row.value))
        except Exception:
            logger.debug("HelperArchive: AppSetting lookup failed", exc_info=True)

        if os.name == "nt":
            candidates.append(Path("H:/xf-helper-archive"))
        else:
            candidates.append(Path("/mnt/xf-helper-archive"))

        for root in candidates:
            if _writable(root):
                return root / self.archive_name, True

        # Local fallback. Always works; create on demand.
        local = LOCAL_FALLBACK_ROOT / self.archive_name
        local.mkdir(parents=True, exist_ok=True)
        return local, False

    def allocate(
        self,
        *,
        size_bytes: int = 0,
        retention_days: int | None = None,
        suffix: str = "",
    ) -> AllocatedFile:
        """Reserve a writable Path.

        Args:
            size_bytes: best-effort hint for disk-pressure pre-flight.
                Falls back to 0 if the caller doesn't know.
            retention_days: how long the file lives before
                ``nightly_data_retention`` prunes it. Defaults from
                ``_DEFAULT_RETENTIONS`` per archive name; falls to 30
                days if the archive is unknown.
            suffix: file extension (".pt", ".npz", ".html.gz", etc.).
        """
        import uuid

        root, is_helper_backed = self._resolve_root()
        root.mkdir(parents=True, exist_ok=True)

        retention = retention_days or _DEFAULT_RETENTIONS.get(self.archive_name, 30)
        file_id = uuid.uuid4().hex[:16]
        filename = f"{file_id}{suffix}"
        path = root / filename

        # Pre-flight disk-pressure guard per DISK-PRESSURE-RULES.md.
        # Best-effort: if the import fails we still return a path.
        if size_bytes > 0:
            try:
                from apps.pipeline.services.disk_pressure import (
                    require_free_disk,
                )

                require_free_disk(estimated_bytes=size_bytes, safety_margin_gb=5)
            except ImportError:
                # disk_pressure module not yet shipped; skip guard.
                pass
            except Exception:
                logger.warning(
                    "HelperArchive: disk-pressure guard failed for %s; proceeding",
                    self.archive_name,
                    exc_info=True,
                )

        # Stash metadata for nightly_data_retention to find later.
        try:
            from apps.core.models import AppSetting
            from django.utils import timezone

            AppSetting.objects.update_or_create(
                key=f"helper_archive.{self.archive_name}.{file_id}",
                defaults={
                    "value": (
                        f"{path}|"
                        f"{timezone.now().isoformat()}|"
                        f"{retention}|"
                        f"{'helper' if is_helper_backed else 'local'}"
                    ),
                },
            )
        except Exception:
            logger.debug(
                "HelperArchive: metadata persist failed for %s",
                self.archive_name,
                exc_info=True,
            )

        return AllocatedFile(
            path=path,
            archive_name=self.archive_name,
            file_id=file_id,
            is_helper_backed=is_helper_backed,
            retention_days=retention,
        )

    def read_path(self, file_id: str) -> Path | None:
        """Return the Path a previously-allocated file lives at, or None."""
        try:
            from apps.core.models import AppSetting

            row = AppSetting.objects.filter(
                key=f"helper_archive.{self.archive_name}.{file_id}"
            ).first()
            if row is None or not row.value:
                return None
            path_str = row.value.split("|", 1)[0]
            return Path(path_str)
        except Exception:
            logger.debug("HelperArchive read_path failed", exc_info=True)
            return None


def _writable(root: Path) -> bool:
    """True if we can write to ``root`` (creates if missing)."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        # Tiny touch-and-delete probe.
        probe = root / ".xf-helper-archive-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:  # noqa: forbidden-pattern silent-except — writability probe; failure means "not writable" which is the answer we return; logging would spam every fallback path.
        return False
