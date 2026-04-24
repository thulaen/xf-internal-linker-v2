"""Process-wide HyperLogLog registry — pick #05 wiring.

Twin of :mod:`apps.sources.bloom_filter_registry` for cardinality
estimation: how many *unique* IDs / URLs has the pipeline ever seen?

Why a separate registry from BloomFilter:

- Different question: "membership" vs "count distinct".
- Different persistence cadence: HLL state is ~12 KB regardless of N
  (vs Bloom's 12 MB at 10M IDs), so the dashboard can read it on
  every page render without paying the Bloom-snapshot's I/O cost.
- Different write cadence: HLL is updated *on every ingestion*, not
  rebuilt weekly. Membership is fine to be slightly stale; cardinality
  is more interesting when it's live.

Snapshot lives at ``var/hll/<bucket>.bin``. Each named bucket has its
own state so the dashboard can show "unique posts ingested this week"
alongside "unique URLs crawled today" without conflating the two
streams.
"""

from __future__ import annotations

import logging
import os
import pickle
import threading
from pathlib import Path

from .hyperloglog import HyperLogLog

logger = logging.getLogger(__name__)


#: Snapshot directory. Each bucket persists at ``<dir>/<bucket>.bin``.
DEFAULT_SNAPSHOT_DIR = Path("var/hll")

#: Standard precision — 12 KB state at p=14 with ~0.8 % relative
#: error. Matches the pick-05 spec default.
DEFAULT_PRECISION: int = 14


class HyperLogLogRegistry:
    """Multi-bucket HLL registry with disk persistence.

    Public API:

    - :meth:`add(bucket, item)` — record an observation. O(1).
    - :meth:`count(bucket)` — current cardinality estimate. Returns 0
      when the bucket has never been observed (cold start).
    - :meth:`snapshot()` — flush all in-memory buckets to disk.
      Called by importers periodically and on graceful shutdown.

    Buckets are keyed by free-form strings (``"unique_posts"``,
    ``"unique_urls_today"``, …). Each gets its own HLL instance and
    its own snapshot file, so dashboards can ask different questions
    of different streams without cross-talk.
    """

    def __init__(
        self,
        *,
        snapshot_dir: Path | None = None,
        precision: int = DEFAULT_PRECISION,
    ) -> None:
        self._snapshot_dir = Path(snapshot_dir or DEFAULT_SNAPSHOT_DIR)
        self._precision = precision
        self._buckets: dict[str, HyperLogLog] = {}
        self._lock = threading.Lock()

    # ── Read API ──────────────────────────────────────────────────

    def count(self, bucket: str) -> int:
        """Return the cardinality estimate for *bucket*.

        Cold start (no in-memory bucket, no on-disk snapshot) returns
        0. Dashboards rendering "0 unique posts seen" while ingestion
        spins up is the expected initial state.
        """
        hll = self._get_or_load(bucket)
        if hll is None:
            return 0
        return hll.count()

    # ── Write API ─────────────────────────────────────────────────

    def add(self, bucket: str, item) -> None:
        """Record *item* in *bucket*. Creates the bucket if missing."""
        hll = self._get_or_load(bucket, create_if_missing=True)
        if hll is not None:
            hll.add(item)

    def snapshot(self, bucket: str | None = None) -> int:
        """Persist *bucket* (or all buckets) to disk. Returns count saved."""
        with self._lock:
            saved = 0
            buckets = (
                [bucket] if bucket is not None else list(self._buckets)
            )
            for key in buckets:
                hll = self._buckets.get(key)
                if hll is None:
                    continue
                if self._save_one(key, hll):
                    saved += 1
            return saved

    # ── Internals ─────────────────────────────────────────────────

    def _get_or_load(
        self, bucket: str, *, create_if_missing: bool = False
    ) -> HyperLogLog | None:
        with self._lock:
            existing = self._buckets.get(bucket)
            if existing is not None:
                return existing
            loaded = self._load_one(bucket)
            if loaded is not None:
                self._buckets[bucket] = loaded
                return loaded
            if create_if_missing:
                hll = HyperLogLog(precision=self._precision)
                self._buckets[bucket] = hll
                return hll
            return None

    def _path_for(self, bucket: str) -> Path:
        # Replace any path-unsafe chars defensively. Buckets are
        # operator-supplied so we can't trust them entirely.
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in bucket)
        return self._snapshot_dir / f"{safe}.bin"

    def _load_one(self, bucket: str) -> HyperLogLog | None:
        path = self._path_for(bucket)
        if not path.exists():
            return None
        try:
            with path.open("rb") as fh:
                obj = pickle.load(fh)
            if not isinstance(obj, HyperLogLog):
                logger.warning(
                    "HyperLogLogRegistry: snapshot %s is not a HyperLogLog",
                    path,
                )
                return None
            return obj
        except (OSError, pickle.UnpicklingError, EOFError) as exc:
            logger.warning(
                "HyperLogLogRegistry: failed to read snapshot %s (%s)",
                path,
                exc,
            )
            return None

    def _save_one(self, bucket: str, hll: HyperLogLog) -> bool:
        path = self._path_for(bucket)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                pickle.dump(hll, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, path)
            return True
        except OSError as exc:
            logger.warning(
                "HyperLogLogRegistry: failed to write snapshot %s (%s)",
                path,
                exc,
            )
            return False


#: Process-wide singleton. Importers, crawler, and dashboard read /
#: write through this same instance.
REGISTRY: HyperLogLogRegistry = HyperLogLogRegistry()
