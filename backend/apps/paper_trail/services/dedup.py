"""Process-singleton wrapper around the C++ papertrail_dedup index.

The C++ extension is the source of truth for near-duplicate detection.
This module owns one lazily-loaded `DedupIndex` per process, persists
it to `/app/data/papertrail.idx` after every mutation, and exposes a
small Python API that the management commands and signals call into.

Falls back gracefully when the extension can't be imported (development
environments without a built C++ wheel) — in that case the wrapper
becomes a no-op so the Django app still boots and tests still run.
"""

from __future__ import annotations

import importlib
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(os.environ.get("PAPERTRAIL_INDEX_PATH", "/app/data/papertrail.idx"))
_lock = threading.Lock()
_index = None  # type: ignore[var-annotated]
_extension_module = None  # type: ignore[var-annotated]
_extension_failed = False


def _load_extension():
    global _extension_module, _extension_failed
    if _extension_module is not None or _extension_failed:
        return _extension_module
    try:
        _extension_module = importlib.import_module("extensions.papertrail_dedup")
    except ImportError as exc:
        _extension_failed = True
        logger.warning(
            "papertrail_dedup extension not importable; dedup is disabled. "
            "Build the extension via setup.py to enable similarity dedup. "
            "Underlying error: %s",
            exc,
        )
    return _extension_module


def _ensure_index():
    global _index
    if _index is not None:
        return _index
    mod = _load_extension()
    if mod is None:
        return None
    with _lock:
        if _index is None:
            _index = mod.DedupIndex()
            if _DEFAULT_PATH.is_file():
                try:
                    _index.load(str(_DEFAULT_PATH))
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "papertrail_dedup: failed to load snapshot at %s; "
                        "starting with empty index",
                        _DEFAULT_PATH,
                        exc_info=True,
                    )
    return _index


def reset_index_for_tests() -> None:
    """Drop the singleton + snapshot. Tests call this in setUp."""
    global _index
    with _lock:
        _index = None
    if _DEFAULT_PATH.is_file():
        try:
            _DEFAULT_PATH.unlink()
        except OSError:
            pass


def _persist(index_obj) -> None:
    try:
        _DEFAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        index_obj.save(str(_DEFAULT_PATH))
    except Exception:  # noqa: BLE001
        logger.warning(
            "papertrail_dedup: failed to persist snapshot to %s",
            _DEFAULT_PATH,
            exc_info=True,
        )


def add_entry(entry_id: int, text: str) -> bool:
    idx = _ensure_index()
    if idx is None:
        return False
    ok = idx.add_entry(int(entry_id), text)
    if ok:
        _persist(idx)
    return ok


def remove_entry(entry_id: int) -> bool:
    idx = _ensure_index()
    if idx is None:
        return False
    ok = idx.remove_entry(int(entry_id))
    if ok:
        _persist(idx)
    return ok


def find_similar(text: str, threshold: float = 0.85) -> list[tuple[int, float]]:
    idx = _ensure_index()
    if idx is None:
        return []
    return list(idx.find_similar(text, float(threshold)))


def has_duplicate(text: str, threshold: float = 0.85) -> bool:
    idx = _ensure_index()
    if idx is None:
        return False
    return bool(idx.has_duplicate(text, float(threshold)))


def size() -> int:
    idx = _ensure_index()
    if idx is None:
        return 0
    return int(idx.size())


def memory_bytes() -> int:
    idx = _ensure_index()
    if idx is None:
        return 0
    return int(idx.memory_bytes())


def save_snapshot(path: Path) -> None:
    idx = _ensure_index()
    if idx is None:
        return
    idx.save(str(path))


def load_snapshot(path: Path) -> None:
    global _index
    mod = _load_extension()
    if mod is None:
        return
    with _lock:
        _index = mod.DedupIndex()
        _index.load(str(path))


def rebuild_from_db() -> int:
    """Re-populate the index from open PaperTrailEntry rows.

    Used on cold start after a snapshot loss or on a fresh container
    where /app/data/papertrail.idx doesn't yet exist.
    """
    from apps.paper_trail.models import PaperTrailEntry

    idx = _ensure_index()
    if idx is None:
        return 0
    count = 0
    qs = PaperTrailEntry.objects.filter(
        status__in=PaperTrailEntry._ACTIVE_STATUSES
    ).only("id", "abstract")
    for entry in qs.iterator():
        if idx.add_entry(int(entry.id), entry.abstract):
            count += 1
    _persist(idx)
    return count
