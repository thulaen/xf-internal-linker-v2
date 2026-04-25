"""Tests for the Roaring-bitmap waste-management primitive.

Covers every public symbol in
``apps.pipeline.services.waste_bitmaps``:

- empty_bitmap / bitmap_from_iterable / bitmap_from_pks (construction)
- bitmap_difference / intersection / union (set algebra)
- cardinality_preview / contains (inspection)
- serialize_bitmap / deserialize_bitmap (persistence)

The DB-backed ``bitmap_from_pks`` test uses Django's TestCase + an
``AppSetting`` model from ``apps.core`` that's safe to instantiate in
tests; the rest are pure-Python and use ``SimpleTestCase``.
"""

from __future__ import annotations

import pyroaring as pr
from django.test import SimpleTestCase, TestCase

from apps.pipeline.services import waste_bitmaps


class EmptyBitmapTests(SimpleTestCase):
    def test_empty_bitmap_is_empty(self) -> None:
        bm = waste_bitmaps.empty_bitmap()
        self.assertIsInstance(bm, pr.BitMap)
        self.assertEqual(len(bm), 0)

    def test_empty_bitmap_returns_fresh_object(self) -> None:
        a = waste_bitmaps.empty_bitmap()
        b = waste_bitmaps.empty_bitmap()
        a.add(1)
        # Mutation must not leak across calls.
        self.assertEqual(len(b), 0)


class BitmapFromIterableTests(SimpleTestCase):
    def test_round_trip_simple_ints(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, 2, 3, 4, 5])
        self.assertEqual(len(bm), 5)
        for value in (1, 2, 3, 4, 5):
            self.assertIn(value, bm)

    def test_dedup(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, 1, 1, 2, 2])
        # Roaring bitmaps are sets — duplicates collapse.
        self.assertEqual(len(bm), 2)

    def test_skips_negative_values(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, -1, 2, -100, 3])
        self.assertEqual(len(bm), 3)
        # Convert to a Python set to bypass pyroaring's __contains__
        # which raises OverflowError on negative ints — exactly the
        # condition the wrapper is meant to absorb.
        self.assertEqual(set(bm), {1, 2, 3})

    def test_skips_non_int_values(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, "two", 2, None, 3])
        self.assertEqual(len(bm), 3)
        self.assertEqual(set(bm), {1, 2, 3})

    def test_skips_uint32_overflow(self) -> None:
        # 2**32 is outside Roaring's uint32 range.
        bm = waste_bitmaps.bitmap_from_iterable([1, 2, 1 << 32, 3])
        self.assertEqual(len(bm), 3)
        # Materialise via set() rather than ``in`` — pyroaring raises
        # OverflowError on out-of-range membership tests.
        self.assertEqual(set(bm), {1, 2, 3})

    def test_empty_iterable_returns_empty_bitmap(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([])
        self.assertEqual(len(bm), 0)

    def test_generator_input(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable(i for i in range(10))
        self.assertEqual(len(bm), 10)


class BitmapFromPksTests(TestCase):
    def test_returns_pks_from_real_queryset(self) -> None:
        from apps.core.models import AppSetting

        # Seed three rows whose PKs we'll then bitmap.
        rows = [
            AppSetting.objects.create(
                key=f"waste_bitmaps_test.{i}",
                value="x",
                description="",
            )
            for i in range(3)
        ]
        bm = waste_bitmaps.bitmap_from_pks(
            AppSetting.objects.filter(key__startswith="waste_bitmaps_test.")
        )
        self.assertEqual(len(bm), 3)
        for row in rows:
            self.assertIn(row.pk, bm)

    def test_empty_queryset_returns_empty_bitmap(self) -> None:
        from apps.core.models import AppSetting

        bm = waste_bitmaps.bitmap_from_pks(
            AppSetting.objects.filter(key="this_key_never_exists")
        )
        self.assertEqual(len(bm), 0)

    def test_failure_returns_empty_bitmap_not_exception(self) -> None:
        # A "queryset" with no .values_list / no .iterator → graceful
        # fallback. The intent is that this never propagates to callers.
        class Broken:
            def values_list(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("simulated DB outage")

        bm = waste_bitmaps.bitmap_from_pks(Broken())
        self.assertEqual(len(bm), 0)


class SetAlgebraTests(SimpleTestCase):
    def test_difference_basic(self) -> None:
        a = waste_bitmaps.bitmap_from_iterable([1, 2, 3, 4])
        b = waste_bitmaps.bitmap_from_iterable([2, 4])
        diff = waste_bitmaps.bitmap_difference(a, b)
        self.assertEqual(set(diff), {1, 3})

    def test_difference_does_not_mutate_inputs(self) -> None:
        a = waste_bitmaps.bitmap_from_iterable([1, 2, 3])
        b = waste_bitmaps.bitmap_from_iterable([2])
        _ = waste_bitmaps.bitmap_difference(a, b)
        self.assertEqual(set(a), {1, 2, 3})
        self.assertEqual(set(b), {2})

    def test_difference_with_empty_exclude_returns_full(self) -> None:
        a = waste_bitmaps.bitmap_from_iterable([1, 2, 3])
        empty = waste_bitmaps.empty_bitmap()
        diff = waste_bitmaps.bitmap_difference(a, empty)
        self.assertEqual(set(diff), {1, 2, 3})

    def test_difference_when_exclude_covers_full_returns_empty(self) -> None:
        a = waste_bitmaps.bitmap_from_iterable([1, 2, 3])
        b = waste_bitmaps.bitmap_from_iterable([1, 2, 3, 4, 5])
        diff = waste_bitmaps.bitmap_difference(a, b)
        self.assertEqual(len(diff), 0)

    def test_intersection_basic(self) -> None:
        a = waste_bitmaps.bitmap_from_iterable([1, 2, 3, 4])
        b = waste_bitmaps.bitmap_from_iterable([3, 4, 5, 6])
        intersect = waste_bitmaps.bitmap_intersection(a, b)
        self.assertEqual(set(intersect), {3, 4})

    def test_intersection_disjoint_is_empty(self) -> None:
        a = waste_bitmaps.bitmap_from_iterable([1, 2])
        b = waste_bitmaps.bitmap_from_iterable([3, 4])
        intersect = waste_bitmaps.bitmap_intersection(a, b)
        self.assertEqual(len(intersect), 0)

    def test_union_basic(self) -> None:
        a = waste_bitmaps.bitmap_from_iterable([1, 2])
        b = waste_bitmaps.bitmap_from_iterable([2, 3])
        union = waste_bitmaps.bitmap_union(a, b)
        self.assertEqual(set(union), {1, 2, 3})


class InspectionTests(SimpleTestCase):
    def test_cardinality_preview_matches_len(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable(range(100))
        self.assertEqual(waste_bitmaps.cardinality_preview(bm), 100)

    def test_cardinality_preview_empty_is_zero(self) -> None:
        bm = waste_bitmaps.empty_bitmap()
        self.assertEqual(waste_bitmaps.cardinality_preview(bm), 0)

    def test_contains_true_when_present(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, 2, 3])
        self.assertTrue(waste_bitmaps.contains(bm, 2))

    def test_contains_false_when_absent(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, 2, 3])
        self.assertFalse(waste_bitmaps.contains(bm, 99))

    def test_contains_negative_returns_false(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, 2, 3])
        # Negative input is invalid for Roaring uint32 — we guard
        # against it silently, no exception.
        self.assertFalse(waste_bitmaps.contains(bm, -5))

    def test_contains_non_int_returns_false(self) -> None:
        bm = waste_bitmaps.bitmap_from_iterable([1, 2, 3])
        self.assertFalse(waste_bitmaps.contains(bm, "two"))


class PersistenceTests(SimpleTestCase):
    def test_round_trip_preserves_bitmap(self) -> None:
        original = waste_bitmaps.bitmap_from_iterable(range(0, 1000, 7))
        blob = waste_bitmaps.serialize_bitmap(original)
        restored = waste_bitmaps.deserialize_bitmap(blob)
        self.assertEqual(set(original), set(restored))
        self.assertEqual(len(original), len(restored))

    def test_round_trip_preserves_empty_bitmap(self) -> None:
        empty = waste_bitmaps.empty_bitmap()
        blob = waste_bitmaps.serialize_bitmap(empty)
        restored = waste_bitmaps.deserialize_bitmap(blob)
        self.assertEqual(len(restored), 0)

    def test_deserialize_empty_bytes_returns_empty(self) -> None:
        # Cold-start safety: ``b""`` is the value an unset
        # AppSetting field would default to; must not raise.
        restored = waste_bitmaps.deserialize_bitmap(b"")
        self.assertIsInstance(restored, pr.BitMap)
        self.assertEqual(len(restored), 0)

    def test_deserialize_garbage_returns_empty(self) -> None:
        # Corrupted blob must not raise to the caller — dashboards
        # render based on this primitive, and one bad row should not
        # crash the page.
        restored = waste_bitmaps.deserialize_bitmap(b"this is not a roaring blob")
        self.assertIsInstance(restored, pr.BitMap)
        self.assertEqual(len(restored), 0)


class ScaleSpotCheckTests(SimpleTestCase):
    """Sanity-check that the wrapper handles realistic prune-set sizes
    without blowing up. Not a benchmark — the dedicated
    ``backend/benchmarks/test_bench_waste_bitmaps.py`` file owns the
    perf-budget assertions."""

    def test_one_million_ids_round_trip(self) -> None:
        big = waste_bitmaps.bitmap_from_iterable(range(0, 1_000_000))
        # Cardinality preview MUST be O(1) — len(bitmap) is enough.
        self.assertEqual(waste_bitmaps.cardinality_preview(big), 1_000_000)
        # Serialise / deserialise round-trip stays correct at scale.
        blob = waste_bitmaps.serialize_bitmap(big)
        restored = waste_bitmaps.deserialize_bitmap(blob)
        self.assertEqual(len(restored), 1_000_000)
