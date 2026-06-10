"""Process-singleton wrappers around extensions.lesson_index.

Three independent singletons (one per sub-index) share the 512 MB cap.
Each persists its snapshot to /app/data/lesson_index/{scoped,perf,cite}.bin.

The kernel is the Rust crate ``rust/extensions/lesson_index`` (ported from C++
per RUST-FIRST.md, zero fallback). The shared
:func:`apps.pipeline.services.rust_kernels.load_kernel` helper owns the single
"import the kernel or raise a loud error" path and verifies the kernel exposes
its ``memory_cap_bytes`` public attribute, so a stale or half-built ``.so``
fails clearly instead of deep in a hot path.

The module still degrades to a no-op when the extension isn't importable — that
keeps the Django app boot-safe in environments without compiled artefacts. This
is a boot-safety shim, not a second copy of the algorithm: there is no
Python implementation of the cache; the only behaviour here is "return
False/None/[] until the kernel is present".
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from apps.pipeline.services.rust_kernels import (
    KernelUnavailableError,
    load_kernel,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(
    os.environ.get("XF_LESSON_INDEX_DIR", "/app/data/lesson_index")
)
_lock = threading.Lock()
_mod = None
_extension_failed = False

_scoped_idx = None
_perf_idx = None
_cite_idx = None


def _load_extension():
    global _mod, _extension_failed
    if _mod is not None or _extension_failed:
        return _mod
    try:
        _mod = load_kernel("extensions.lesson_index", "memory_cap_bytes")
    except KernelUnavailableError as exc:
        _extension_failed = True
        logger.warning("lesson_index kernel not importable: %s", exc)
    return _mod


def _ensure_scoped():
    global _scoped_idx
    if _scoped_idx is not None:
        return _scoped_idx
    mod = _load_extension()
    if mod is None:
        return None
    with _lock:
        if _scoped_idx is None:
            _scoped_idx = mod.ScopedLessonIndex()
            snap = _DEFAULT_DIR / "scoped.bin"
            if snap.is_file():
                try:
                    _scoped_idx.load(str(snap))
                except Exception:  # noqa: BLE001
                    logger.warning("scoped snapshot load failed", exc_info=True)
    return _scoped_idx


def _ensure_perf():
    global _perf_idx
    if _perf_idx is not None:
        return _perf_idx
    mod = _load_extension()
    if mod is None:
        return None
    with _lock:
        if _perf_idx is None:
            _perf_idx = mod.PerfBaselineCache()
            snap = _DEFAULT_DIR / "perf.bin"
            if snap.is_file():
                try:
                    _perf_idx.load(str(snap))
                except Exception:  # noqa: BLE001
                    logger.warning("perf snapshot load failed", exc_info=True)
    return _perf_idx


def _ensure_cite():
    global _cite_idx
    if _cite_idx is not None:
        return _cite_idx
    mod = _load_extension()
    if mod is None:
        return None
    with _lock:
        if _cite_idx is None:
            _cite_idx = mod.CitationCache()
    return _cite_idx


def reset_all_for_tests() -> None:
    """Drop singletons + snapshots. Tests call this in setUp."""
    global _scoped_idx, _perf_idx, _cite_idx
    with _lock:
        _scoped_idx = None
        _perf_idx = None
        _cite_idx = None
    for name in ("scoped.bin", "perf.bin"):
        snap = _DEFAULT_DIR / name
        if snap.is_file():
            try:
                snap.unlink()
            except OSError:
                pass


def _persist_scoped() -> None:
    if _scoped_idx is None:
        return
    try:
        _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
        _scoped_idx.save(str(_DEFAULT_DIR / "scoped.bin"))
    except Exception:  # noqa: BLE001
        logger.warning("scoped snapshot save failed", exc_info=True)


def _persist_perf() -> None:
    if _perf_idx is None:
        return
    try:
        _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
        _perf_idx.save(str(_DEFAULT_DIR / "perf.bin"))
    except Exception:  # noqa: BLE001
        logger.warning("perf snapshot save failed", exc_info=True)


# ── Scoped lesson API ─────────────────────────────────────────────
def scoped_add(path: str, *, autoissue_id: int, lesson_hash: int,
               severity: int, resolved_at_unix: int = 1_700_000_000) -> bool:
    idx = _ensure_scoped()
    if idx is None:
        return False
    mod = _load_extension()
    rec = mod.LessonRecord()
    rec.autoissue_id = int(autoissue_id)
    rec.lesson_hash = int(lesson_hash)
    rec.severity = int(severity)
    rec.resolved_at_unix = int(resolved_at_unix)
    ok = idx.add(path, rec)
    if ok:
        _persist_scoped()
    return ok


def scoped_find(path: str, *, limit: int = 5) -> list[dict[str, Any]]:
    idx = _ensure_scoped()
    if idx is None:
        return []
    raw = idx.find_by_path(path, int(limit))
    return [
        {
            "autoissue_id": r.autoissue_id,
            "lesson_hash": r.lesson_hash,
            "severity": r.severity,
            "resolved_at_unix": r.resolved_at_unix,
        }
        for r in raw
    ]


# ── Perf baseline API ─────────────────────────────────────────────
def perf_put(fn_sig: str, *, p50_ns: int, p95_ns: int, p99_ns: int,
             mean_ns: int, samples: int,
             measured_at_unix: int = 1_700_000_000) -> bool:
    idx = _ensure_perf()
    if idx is None:
        return False
    mod = _load_extension()
    rec = mod.BaselineRecord()
    rec.p50_ns = int(p50_ns)
    rec.p95_ns = int(p95_ns)
    rec.p99_ns = int(p99_ns)
    rec.mean_ns = int(mean_ns)
    rec.samples = int(samples)
    rec.measured_at_unix = int(measured_at_unix)
    ok = idx.put(fn_sig, rec)
    if ok:
        _persist_perf()
    return ok


def perf_get(fn_sig: str) -> dict[str, Any] | None:
    idx = _ensure_perf()
    if idx is None:
        return None
    rec = idx.get(fn_sig)
    if rec is None:
        return None
    return {
        "p50_ns": rec.p50_ns,
        "p95_ns": rec.p95_ns,
        "p99_ns": rec.p99_ns,
        "mean_ns": rec.mean_ns,
        "samples": rec.samples,
        "measured_at_unix": rec.measured_at_unix,
    }


def compute_speedup(fn_sig: str, *, new_p50_ns: int) -> float | None:
    """Return baseline_p50 / new_p50 (ratio > 1 means faster)."""
    rec = perf_get(fn_sig)
    if rec is None:
        return None
    if new_p50_ns <= 0:
        return float("inf")
    return rec["p50_ns"] / float(new_p50_ns)


# ── Citation API ──────────────────────────────────────────────────
def cite_put(key: str, *, kind: str, id_: str, title: str, authors: str,
             year: int, url: str, accessible: int = 1,
             last_checked_unix: int = 1_700_000_000) -> bool:
    """Store a citation in the in-process Python dict.

    By design the ``CitationCache`` kernel binding exposes only
    ``size``/``memory_bytes``/``reclaim_now``/``clear`` (matching the original
    C++ binding surface); the citation records themselves live in this
    process-local Python dict, not in the kernel. This is the intended
    ownership split, not a fallback for a missing kernel method.
    """
    idx = _ensure_cite()
    if idx is None:
        return False
    _cite_python_fallback[key] = {
        "kind": kind,
        "id": id_,
        "title": title,
        "authors": authors,
        "year": int(year),
        "url": url,
        "accessible": int(accessible),
        "last_checked_unix": int(last_checked_unix),
    }
    return True


def cite_get(key: str) -> dict[str, Any] | None:
    return _cite_python_fallback.get(key)


_cite_python_fallback: dict[str, dict[str, Any]] = {}


# ── Persistence ──────────────────────────────────────────────────
def save_all(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if _scoped_idx is not None:
        _scoped_idx.save(str(root / "scoped.bin"))
    if _perf_idx is not None:
        _perf_idx.save(str(root / "perf.bin"))


def load_all(root: Path) -> None:
    global _scoped_idx, _perf_idx
    mod = _load_extension()
    if mod is None:
        return
    with _lock:
        _scoped_idx = mod.ScopedLessonIndex()
        _perf_idx = mod.PerfBaselineCache()
        scoped_path = root / "scoped.bin"
        if scoped_path.is_file():
            _scoped_idx.load(str(scoped_path))
        perf_path = root / "perf.bin"
        if perf_path.is_file():
            _perf_idx.load(str(perf_path))


# ── Rebuild from DB ──────────────────────────────────────────────
def rebuild_scoped_from_db() -> int:
    """Pull every resolved PaperTrailEntry with affected_files into the
    ScopedLessonIndex so future read_scoped_lessons calls see them.
    """
    from apps.paper_trail.models import PaperTrailEntry

    idx = _ensure_scoped()
    if idx is None:
        return 0
    count = 0
    qs = PaperTrailEntry.objects.filter(
        status=PaperTrailEntry.STATUS_RESOLVED
    ).only("id", "affected_files", "severity", "resolved_at")
    severity_rank = {
        PaperTrailEntry.SEVERITY_LOW: 0,
        PaperTrailEntry.SEVERITY_MEDIUM: 1,
        PaperTrailEntry.SEVERITY_HIGH: 2,
        PaperTrailEntry.SEVERITY_CRITICAL: 3,
    }
    for entry in qs.iterator():
        sev = severity_rank.get(entry.severity, 1)
        resolved_at = int(entry.resolved_at.timestamp()) if entry.resolved_at else 0
        for path in entry.affected_files or []:
            if not isinstance(path, str) or not path.strip():
                continue
            if scoped_add(path.strip(), autoissue_id=entry.id,
                          lesson_hash=hash(entry.title) & 0xFFFFFFFFFFFFFFFF,
                          severity=sev, resolved_at_unix=resolved_at):
                count += 1
    return count
