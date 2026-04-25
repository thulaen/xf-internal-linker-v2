"""Integration test for pick #24 — PMI / NPMI wiring into the co-occurrence upsert.

Proof point: ``_upsert_cooccurrence_pairs`` now persists two more
columns alongside the existing G²: ``pmi_score`` and ``npmi_score``,
both computed from the same ``co_count``/``a_total``/``b_total``/
``total_sessions`` quadruple. We feed the helper a small fixture of
co-counts and assert the persisted scores match what the
``apps.sources.collocations`` helper returns directly — proves the
two statistics are computed from the same counts (no duplicate
collection work) and that the wiring is correct.
"""

from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.content.models import ContentItem
from apps.cooccurrence.models import SessionCoOccurrencePair
from apps.cooccurrence.services import _upsert_cooccurrence_pairs


class PmiUpsertWiringTests(TestCase):
    def setUp(self) -> None:
        # Two ContentItems so the SessionCoOccurrencePair foreign keys resolve.
        self.a = ContentItem.objects.create(
            content_id=701,
            content_type="thread",
            title="A",
        )
        self.b = ContentItem.objects.create(
            content_id=702,
            content_type="thread",
            title="B",
        )

    def _persist(self, *, co_count: int, a_total: int, b_total: int, total: int):
        return _upsert_cooccurrence_pairs(
            co_counts={(self.a.pk, self.b.pk): co_count},
            marginal_counts={self.a.pk: a_total, self.b.pk: b_total},
            total_sessions=total,
            min_co_session_count=1,
            min_jaccard=0.0,
            window_start=date(2026, 1, 1),
            window_end=date(2026, 1, 7),
        )

    def test_pmi_columns_populated(self) -> None:
        """A genuine pair persists pmi_score / npmi_score alongside g²."""
        from apps.sources.collocations import normalised_pmi, pmi

        # 100 sessions: 30 saw A, 25 saw B, 20 saw both → high co-occurrence.
        written = self._persist(co_count=20, a_total=30, b_total=25, total=100)
        self.assertEqual(written, 1)

        pair = SessionCoOccurrencePair.objects.get(
            source_content_item=self.a, dest_content_item=self.b
        )
        # The persisted PMI / NPMI must match what the helper would
        # compute from the same counts (within the rounding the
        # service applies — 4 decimal places).
        expected_pmi = pmi(joint_count=20, count_a=30, count_b=25, total=100)
        expected_npmi = normalised_pmi(
            joint_count=20, count_a=30, count_b=25, total=100
        )
        self.assertAlmostEqual(pair.pmi_score, round(expected_pmi, 4), places=4)
        self.assertAlmostEqual(pair.npmi_score, round(expected_npmi, 4), places=4)

    def test_pmi_positive_for_associated_pair(self) -> None:
        """Above-chance co-occurrence yields positive PMI (sanity check)."""
        self._persist(co_count=15, a_total=20, b_total=20, total=50)
        pair = SessionCoOccurrencePair.objects.get(
            source_content_item=self.a, dest_content_item=self.b
        )
        # 15/50 joint vs (20/50)*(20/50) = 0.16 expected → PMI > 0.
        self.assertGreater(pair.pmi_score, 0.0)
        # NPMI is bounded to [-1, 1] — strong association means close to 1.
        self.assertGreater(pair.npmi_score, 0.0)
        self.assertLessEqual(pair.npmi_score, 1.0)

    def test_existing_columns_unchanged(self) -> None:
        """The G² wiring is preserved alongside the new PMI/NPMI fields."""
        from apps.cooccurrence.services import _compute_log_likelihood

        self._persist(co_count=10, a_total=20, b_total=15, total=80)
        pair = SessionCoOccurrencePair.objects.get(
            source_content_item=self.a, dest_content_item=self.b
        )
        expected_g2 = _compute_log_likelihood(10, 20, 15, 80)
        self.assertAlmostEqual(pair.log_likelihood_score, round(expected_g2, 4), places=4)
        # And the older Jaccard / lift columns still land too.
        self.assertGreater(pair.jaccard_similarity, 0.0)
        self.assertGreater(pair.lift, 0.0)
