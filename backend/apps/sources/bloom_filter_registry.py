"""Process-wide Bloom-filter registry — pick #04 wiring.

The :class:`apps.sources.bloom_filter.BloomFilter` is a fast in-memory
helper. To make it useful in production we need:

1. **Persistence** — the W1 ``bloom_filter_ids_rebuild`` scheduled job
   builds the filter once a week. Without persistence the rebuilt
   filter is garbage-collected at job completion and the next callers
   start cold.
2. **A read API** — import-pipeline callers want
   ``"have I seen this post id?"`` answered in O(1) without each
   caller reconstructing the filter from scratch.

This module provides both. Snapshot file lives at
``var/bloom/content_ids.bin``. The W1 job rebuilds + saves; readers
load lazily on first use and reload on cache-miss.

Two-process safety: each Django/Celery process loads its own copy.
That's fine for dedup — false negatives are intolerable, false
positives are tolerable, and a stale snapshot can only produce false
*positives* (we miss a freshly-imported id), which is the safe
direction.
"""

from __future__ import annotations

import logging
import os
import pickle
import threading
from pathlib import Path

from .bloom_filter import BloomFilter

logger = logging.getLogger(__name__)


#: Snapshot path. Created in the project's `var/` tree alongside
#: optuna's meta_hpo.db so all runtime artefacts stay in one place.
DEFAULT_SNAPSHOT_PATH = Path("var/bloom/content_ids.bin")


class BloomFilterRegistry:
    """Thread-safe lazy-loaded singleton wrapper.

    Public API:

    - :meth:`is_known(content_pk)` — O(1) membership test. Returns
      ``False`` (not "unknown") when no snapshot exists yet, so
      callers can use it as a fast-skip check without special-casing
      cold start.
    - :meth:`mark(content_pk)` — adds an ID to the in-memory filter.
      Does NOT immediately persist; the next ``rebuild_from_db()``
      call is the durable write path.
    - :meth:`rebuild_from_db(*, capacity, fp_rate)` — full rebuild
      from the authoritative ``ContentItem`` table. Replaces the
      in-memory filter atomically and saves a snapshot.
    """

    def __init__(self, snapshot_path: Path | None = None) -> None:
        self._snapshot_path = Path(snapshot_path or DEFAULT_SNAPSHOT_PATH)
        self._filter: BloomFilter | None = None
        self._lock = threading.Lock()
        self._loaded = False

    # ── Read API ──────────────────────────────────────────────────

    def is_known(self, content_pk: int | str) -> bool:
        """Return True iff the snapshot has seen this id.

        Cold start (no snapshot yet) returns False — the caller treats
        the id as new, which is the safe direction (no skip = no data
        loss, just an extra DB lookup).
        """
        bf = self._filter_or_load()
        if bf is None:
            return False
        return str(content_pk) in bf

    def mark(self, content_pk: int | str) -> None:
        """Add *content_pk* to the in-memory filter.

        Persistence happens on the next ``rebuild_from_db()`` call.
        Inline ``mark`` is for "I just imported this id" hot paths
        that want subsequent reads in the same process to fast-skip.
        """
        bf = self._filter_or_load(create_if_missing=True)
        if bf is not None:
            bf.add(str(content_pk))

    # ── Write API (W1 scheduled job) ──────────────────────────────

    def rebuild_from_db(
        self,
        *,
        capacity: int | None = None,
        fp_rate: float = 0.01,
        progress: callable | None = None,
    ) -> int:
        """Rebuild from the authoritative ContentItem table.

        Used by the weekly ``bloom_filter_ids_rebuild`` scheduled job
        (W1). Returns the number of IDs added.

        ``capacity`` defaults to ``max(2 * actual_count, 10_000)`` so
        the filter has room before its FPR drifts. Callers can pin a
        specific size for stable cross-run behaviour.
        ``progress(done, total)`` is an optional callback for the
        runner's checkpoint reporter.
        """
        from apps.content.models import ContentItem

        total = ContentItem.objects.filter(is_deleted=False).count()
        if total == 0:
            logger.info("BloomFilterRegistry.rebuild_from_db: no content items")
            return 0
        if capacity is None:
            capacity = max(2 * total, 10_000)

        bf = BloomFilter(capacity=capacity, false_positive_rate=fp_rate)
        done = 0
        for content_pk in (
            ContentItem.objects.filter(is_deleted=False)
            .values_list("pk", flat=True)
            .iterator(chunk_size=10_000)
        ):
            bf.add(str(content_pk))
            done += 1
            if progress and done % 50_000 == 0:
                progress(done, total)

        with self._lock:
            self._filter = bf
            self._loaded = True
            self._save_snapshot()
        return done

    # ── Internals ─────────────────────────────────────────────────

    def _filter_or_load(self, *, create_if_missing: bool = False) -> BloomFilter | None:
        with self._lock:
            if self._filter is not None:
                return self._filter
            if self._loaded and not create_if_missing:
                # We already tried to load and there was no snapshot.
                return None
            loaded = self._load_snapshot()
            if loaded is not None:
                self._filter = loaded
                self._loaded = True
                return self._filter
            self._loaded = True
            if create_if_missing:
                self._filter = BloomFilter(
                    capacity=10_000_000, false_positive_rate=0.01
                )
                return self._filter
            return None

    def _load_snapshot(self) -> BloomFilter | None:
        if not self._snapshot_path.exists():
            return None
        try:
            with self._snapshot_path.open("rb") as fh:
                obj = pickle.load(fh)
            if not isinstance(obj, BloomFilter):
                logger.warning(
                    "BloomFilterRegistry: snapshot at %s is not a BloomFilter",
                    self._snapshot_path,
                )
                return None
            return obj
        except (OSError, pickle.UnpicklingError, EOFError) as exc:
            logger.warning(
                "BloomFilterRegistry: failed to read snapshot %s (%s) — "
                "starting cold",
                self._snapshot_path,
                exc,
            )
            return None

    def _save_snapshot(self) -> None:
        if self._filter is None:
            return
        try:
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._snapshot_path.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                pickle.dump(self._filter, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, self._snapshot_path)
        except OSError as exc:
            logger.warning(
                "BloomFilterRegistry: failed to write snapshot %s (%s)",
                self._snapshot_path,
                exc,
            )


#: Process-wide singleton. Importers and the W1 scheduled job both
#: reach in here so reads + rebuilds share one snapshot path.
REGISTRY: BloomFilterRegistry = BloomFilterRegistry()
