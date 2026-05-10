"""Atomic Parquet read/write helpers for weekly model snapshots.

Why this module exists:
  Two weekly retrain jobs (Node2Vec embeddings, BPR ranking weights) need to
  save their output to disk and survive both crashes mid-write and a disk
  that's too full. Without a shared helper each writer would copy-paste the
  ``write to .tmp + os.replace`` dance plus the disk-pressure pre-flight.

Atomicity:
  ``write_parquet_atomic()`` writes to a sibling ``.tmp`` file then calls
  ``os.replace()``. POSIX ``rename`` and Windows ``MoveFileExW`` are both
  atomic within a single filesystem, so a crash mid-write leaves either the
  old file or the new file — never a corrupt half-written file. Reference:
  POSIX.1-2017 §3.215 "Path Resolution" and Microsoft Win32
  ``MoveFileEx(MOVEFILE_REPLACE_EXISTING)`` documentation.

Disk pressure:
  Pre-flights large writes via ``apps.pipeline.services.disk_pressure
  .require_free_disk()``. The module shipped 2026-05-09 and now performs the
  real watermark check. The defensive ``ImportError`` catch in
  ``_try_disk_pressure_guard`` is retained as a pure safety net for tests
  that mock the import out.

Backward-compatible reads:
  ``read_parquet_or_legacy()`` tries Parquet first, falls back to a caller-
  supplied legacy loader callback. After the first weekly retrain post-deploy
  the legacy file becomes redundant. We log a one-time warning on the legacy
  branch so the cutover is visible.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_legacy_warning_emitted: set[str] = set()


def _try_disk_pressure_guard(estimated_bytes: int, *, safety_margin_gb: int = 2) -> None:
    """Disk-pressure pre-flight. Raises DiskPressureError on insufficient free space.

    The module ships in the same commit as DISK-PRESSURE-RULES.md so the only
    way we hit ImportError is when a test explicitly mocks it out — keep the
    catch as a defensive net but never silently swallow other exceptions.
    """
    try:
        from apps.pipeline.services.disk_pressure import require_free_disk

        require_free_disk(estimated_bytes=estimated_bytes, safety_margin_gb=safety_margin_gb)
    except ImportError:
        logger.debug("disk_pressure module unavailable; skipping pre-flight guard")


def write_parquet_atomic(df: Any, path: str | Path, *, estimated_bytes: int | None = None) -> None:
    """Write a Polars DataFrame to ``path`` atomically.

    Writes to ``<path>.tmp`` first, then atomically renames it onto ``path``.
    On crash mid-write the original ``path`` is untouched; the ``.tmp`` file
    may be left behind and is harmless (overwritten on next successful write).

    ``estimated_bytes`` enables the disk-pressure pre-flight; pass the rough
    expected file size if you have it. Falls back to ``len(df) * 64`` when
    omitted (a safe over-estimate for typical embedding tables).
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if estimated_bytes is None:
        try:
            estimated_bytes = max(1, len(df)) * 64
        except Exception:  # noqa: BLE001 — defensive: df may not implement __len__; default to 1 MB pre-flight ceiling.
            estimated_bytes = 1 * 1024 * 1024
    _try_disk_pressure_guard(estimated_bytes)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    df.write_parquet(str(tmp_path))
    os.replace(str(tmp_path), str(target))


def read_parquet_or_legacy(
    path: str | Path,
    *,
    legacy_loader: Callable[[], Any],
    legacy_label: str = "legacy",
):
    """Read ``path`` as Parquet; fall back to ``legacy_loader()`` if missing.

    Logs a one-time warning per ``legacy_label`` when the legacy branch is
    taken, so a future weekly retrain that finally produces the Parquet file
    is visible by the absence of the warning.
    """
    target = Path(path)
    if target.exists():
        try:
            import polars as pl

            return pl.read_parquet(str(target))
        except Exception as exc:  # noqa: BLE001 — Parquet read failed (corrupt file?); fall through to legacy and log.
            logger.warning(
                "Parquet read failed at %s (%s); falling back to %s loader",
                target,
                exc,
                legacy_label,
            )
    if legacy_label not in _legacy_warning_emitted:
        logger.warning(
            "Parquet snapshot not found at %s — using %s loader. "
            "This warning fires once per process; expect it to disappear after "
            "the next weekly retrain writes a Parquet file.",
            target,
            legacy_label,
        )
        _legacy_warning_emitted.add(legacy_label)
    return legacy_loader()


__all__ = [
    "write_parquet_atomic",
    "read_parquet_or_legacy",
]
