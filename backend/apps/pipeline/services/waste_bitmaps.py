"""Roaring-bitmap-backed waste-management primitive.

Reference
---------
Lemire, D., Kaser, O., Kurz, N., Deri, L., O'Hara, C., Saint-Jacques,
F., Ssi-Yan-Kai, G. (2018). "Roaring Bitmaps: Implementation of an
Optimized Software Library." *Software: Practice and Experience*,
48(4), 867-895. DOI 10.1002/spe.2560.

Earlier paper: Chambi, S., Lemire, D., Kaser, O., Godin, R. (2016).
"Better bitmap performance with Roaring bitmaps." *Software:
Practice and Experience*, 46(5), 709-719.

Library: CRoaring (C++) at https://github.com/RoaringBitmap/CRoaring
(MIT). Python binding: ``pyroaring`` 1.0.4, already pinned in
``backend/requirements.txt``.

Goal
----
Every waste-management item (B.5/B.6/B.7 retention pruning, G3.1
content-signature compute, A.1 host-token-bag dedup, C.2 cascade-
relevance per-destination tracking) needs the same four operations:

1. **Set membership** — is row N already in this collection?
2. **Set difference** — rows in A but not in B (the "rows to delete"
   set when comparing the full table to a "keep" filter).
3. **Set union / intersection** — rows seen across multiple sources.
4. **Cardinality** — how many rows would the prune affect, BEFORE
   running the SQL DELETE? Lets the dashboard show "12,480 rows
   pending" without touching the prune itself.

Roaring bitmaps give all four in O(min(|A|, |B|)) time using ~50 KB
RAM per 100k IDs and ~1 MB per 10M IDs (Lemire 2018 §6 benchmark).
At the linker's scale (≤ 1M rows total) we stay well under 1 MB
even with five bitmaps live concurrently — comfortably inside the
128 MB RAM cap from the operator constraints.

This module is a thin, documented wrapper. Call sites import the
named functions; they should never touch ``pyroaring.BitMap``
directly — keeping the surface narrow means a future swap to
another set-algebra library is one file's worth of work.

Cold-start safety
-----------------
Every public function returns a sensible empty value on failure:

- An empty queryset / iterable → empty ``BitMap()`` (cardinality 0).
- A failed DB read → empty ``BitMap()`` and a warning logged.
- A corrupted serialised blob → empty ``BitMap()`` (no exception
  raised to the caller).

Callers can therefore unconditionally call into this module without
``try``/``except`` boilerplate.
"""

from __future__ import annotations

import logging
from typing import Iterable

import pyroaring as pr

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Construction
# ─────────────────────────────────────────────────────────────────────


def empty_bitmap() -> pr.BitMap:
    """Return a fresh, empty Roaring bitmap.

    Used as the cold-start fallback by every other helper. Pulling
    the constructor through one named function makes the empty case
    explicit at every call site.
    """
    return pr.BitMap()


def bitmap_from_iterable(values: Iterable[int]) -> pr.BitMap:
    """Build a Roaring bitmap from any iterable of non-negative ints.

    Roaring stores 32-bit unsigned ints, so values must fit in
    ``[0, 2**32)``. Negative values are skipped with a warning to
    keep the call site cold-start safe even when feeding it a mixed
    list.

    Cold-start safe: an empty iterable returns an empty bitmap.
    """
    bitmap = pr.BitMap()
    skipped = 0
    for value in values:
        if not isinstance(value, int) or value < 0 or value >= (1 << 32):
            skipped += 1
            continue
        bitmap.add(value)
    if skipped:
        logger.warning(
            "waste_bitmaps.bitmap_from_iterable skipped %d out-of-range "
            "value(s); Roaring requires uint32",
            skipped,
        )
    return bitmap


def bitmap_from_pks(queryset) -> pr.BitMap:
    """Build a Roaring bitmap from the primary keys of *queryset*.

    The caller defines the filter (e.g. ``Suggestion.objects.filter(
    updated_at__lt=cutoff)``); this helper just walks the resulting
    primary keys and packs them into a Roaring bitmap.

    Uses ``.values_list("pk", flat=True).iterator()`` so the whole
    queryset never materialises in memory — fine for million-row
    prune sets.

    Cold-start safe: any exception (DB unreachable, ORM not
    initialised, malformed queryset) is caught and an empty bitmap
    is returned with a warning logged.
    """
    bitmap = pr.BitMap()
    try:
        # ``.iterator()`` streams rows without ORM caching, so the
        # full queryset never materialises in memory — important for
        # million-row prune sets.
        for pk in queryset.values_list("pk", flat=True).iterator():
            if pk is None:
                continue
            try:
                bitmap.add(int(pk))
            except (ValueError, OverflowError):
                logger.warning(
                    "waste_bitmaps.bitmap_from_pks skipping non-uint32 pk %r",
                    pk,
                )
    except Exception as exc:  # pragma: no cover — DB-unreachable path
        logger.warning(
            "waste_bitmaps.bitmap_from_pks failed: %s", exc, exc_info=True
        )
        return pr.BitMap()
    return bitmap


# ─────────────────────────────────────────────────────────────────────
# Set algebra
# ─────────────────────────────────────────────────────────────────────


def bitmap_difference(big: pr.BitMap, exclude: pr.BitMap) -> pr.BitMap:
    """Return ids in *big* that are NOT in *exclude*.

    Used to compute "rows we plan to delete" by starting with the
    full set and excluding rows that should be kept (recent rows,
    approved Suggestions, etc.). O(min(|big|, |exclude|)) per the
    Roaring paper.

    Both inputs are unmodified. Returns a new bitmap.
    """
    return big - exclude


def bitmap_intersection(a: pr.BitMap, b: pr.BitMap) -> pr.BitMap:
    """Return ids present in BOTH *a* and *b*. O(min(|a|, |b|))."""
    return a & b


def bitmap_union(a: pr.BitMap, b: pr.BitMap) -> pr.BitMap:
    """Return ids present in EITHER *a* or *b*. O(|a| + |b|)."""
    return a | b


# ─────────────────────────────────────────────────────────────────────
# Inspection
# ─────────────────────────────────────────────────────────────────────


def cardinality_preview(bitmap: pr.BitMap) -> int:
    """Return the number of rows in *bitmap*.

    O(1) per the Roaring spec — the cardinality is maintained
    incrementally as values are added. The dashboard's
    "rows pending prune" counter calls this on every refresh.
    """
    return len(bitmap)


def contains(bitmap: pr.BitMap, value: int) -> bool:
    """Return True when *value* is in *bitmap*. O(log n) at worst."""
    if not isinstance(value, int) or value < 0:
        return False
    return value in bitmap


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────


def serialize_bitmap(bitmap: pr.BitMap) -> bytes:
    """Return a portable byte representation of *bitmap*.

    Backed by the CRoaring serialisation format (Lemire 2018 §5),
    which is stable across pyroaring releases and across machine
    endianness. The resulting bytes are safe to store in an
    ``AppSetting`` row, a Redis key, or a pickle.

    Cold-start safe: an empty bitmap serialises to a tiny non-empty
    header — the deserialiser knows to reconstruct an empty bitmap.
    """
    return bitmap.serialize()


def deserialize_bitmap(blob: bytes) -> pr.BitMap:
    """Inverse of :func:`serialize_bitmap`.

    Cold-start safe: ``b""`` (empty) returns an empty bitmap rather
    than raising. A corrupted blob also returns an empty bitmap (and
    logs a warning) so a single corrupt AppSetting row doesn't crash
    the dashboard.
    """
    if not blob:
        return pr.BitMap()
    try:
        return pr.BitMap.deserialize(blob)
    except Exception as exc:  # pragma: no cover — corrupted-blob path
        logger.warning(
            "waste_bitmaps.deserialize_bitmap failed (%d bytes): %s",
            len(blob),
            exc,
        )
        return pr.BitMap()


# ─────────────────────────────────────────────────────────────────────
# Module surface — kept narrow on purpose so a future library swap
# is a one-file change.
# ─────────────────────────────────────────────────────────────────────

__all__ = [
    "empty_bitmap",
    "bitmap_from_iterable",
    "bitmap_from_pks",
    "bitmap_difference",
    "bitmap_intersection",
    "bitmap_union",
    "cardinality_preview",
    "contains",
    "serialize_bitmap",
    "deserialize_bitmap",
]
