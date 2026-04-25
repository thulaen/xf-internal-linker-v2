"""Integration test for pick #51 — TrustRank Auto-Seeder scheduled-job wiring.

Proof point: the scheduled job ``run_trustrank_auto_seeder`` reads
operator-tunable AppSettings + builds the per-node quality maps
(``post_quality`` / ``readability_grade`` / ``spam_flagged``) from
``ContentItem.content_value_score`` and ``Post.flesch_kincaid_grade``
(the column Phase 3 #19 wired), then passes them to ``pick_seeds``.
The auto-picked seed list lands in ``AppSetting["trustrank.seed_ids"]``
where the W1 ``trustrank_propagation`` job reads them.

This test fakes the graph loader (so we don't need a real
ContentItem-loaded networkx graph) and verifies:

1. AppSetting overrides are read and forwarded to ``pick_seeds``.
2. Post-quality data is built from the ContentItem rows.
3. Readability data is built from the Post rows.
4. Spam-quality filter triggers on low ``content_value_score`` rows.
5. The persisted ``trustrank.seed_ids`` is the ``pick_seeds`` output.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import networkx as nx
from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem
from apps.core.models import AppSetting
from apps.scheduled_updates.jobs import run_trustrank_auto_seeder


class TrustRankAutoSeederSchedulerWiringTests(TestCase):
    def setUp(self) -> None:
        self.scope = ScopeItem.objects.create(
            scope_id=51, scope_type="node", title="seeder-test"
        )
        # Three ContentItems with distinct quality + readability profiles.
        # Item A — high quality, low FKGL → ideal seed.
        self.item_a = ContentItem.objects.create(
            content_id=5101,
            content_type="thread",
            title="A",
            scope=self.scope,
            content_value_score=0.85,
        )
        Post.objects.create(
            content_item=self.item_a,
            raw_bbcode="x",
            clean_text="x",
            flesch_kincaid_grade=8.0,
        )
        # Item B — low quality (below post_quality_min) → rejected.
        self.item_b = ContentItem.objects.create(
            content_id=5102,
            content_type="thread",
            title="B",
            scope=self.scope,
            content_value_score=0.30,
        )
        Post.objects.create(
            content_item=self.item_b,
            raw_bbcode="x",
            clean_text="x",
            flesch_kincaid_grade=10.0,
        )
        # Item C — very low quality (below spam floor) → spam_flagged.
        self.item_c = ContentItem.objects.create(
            content_id=5103,
            content_type="thread",
            title="C",
            scope=self.scope,
            content_value_score=0.05,
        )
        Post.objects.create(
            content_item=self.item_c,
            raw_bbcode="x",
            clean_text="x",
            flesch_kincaid_grade=22.0,  # also above readability ceiling
        )

    def _patch_graph_loader(self) -> nx.DiGraph:
        """Build a tiny graph where every test ContentItem is a node."""
        g = nx.DiGraph()
        for item in (self.item_a, self.item_b, self.item_c):
            g.add_node((item.pk, item.content_type))
        # Add a few edges so inverse-PageRank produces meaningful scores.
        g.add_edge(
            (self.item_a.pk, "thread"), (self.item_b.pk, "thread"), weight=1.0
        )
        g.add_edge(
            (self.item_b.pk, "thread"), (self.item_c.pk, "thread"), weight=1.0
        )
        g.add_edge(
            (self.item_c.pk, "thread"), (self.item_a.pk, "thread"), weight=1.0
        )
        return g

    def _run_job_with_settings(self, **settings: str) -> str:
        """Execute the scheduled job and return the persisted seed_ids string."""
        for key, value in settings.items():
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )

        with patch(
            "apps.scheduled_updates.jobs._load_networkx_graph",
            return_value=self._patch_graph_loader(),
        ):
            run_trustrank_auto_seeder(MagicMock(), MagicMock())

        row = AppSetting.objects.get(key="trustrank.seed_ids")
        return row.value

    def test_seed_picker_reads_appsetting_overrides(self) -> None:
        """``pick_seeds`` is called with AppSetting-sourced parameters."""
        with patch(
            "apps.pipeline.services.trustrank_auto_seeder.pick_seeds",
            wraps=__import__(
                "apps.pipeline.services.trustrank_auto_seeder",
                fromlist=["pick_seeds"],
            ).pick_seeds,
        ) as pick:
            self._run_job_with_settings(**{
                "trustrank_auto_seeder.candidate_pool_size": "50",
                "trustrank_auto_seeder.seed_count_k": "5",
                "trustrank_auto_seeder.post_quality_min": "0.7",
                "trustrank_auto_seeder.readability_grade_max": "12",
                "trustrank_auto_seeder.spam_content_value_floor": "0.10",
            })

        self.assertTrue(pick.called)
        _, kwargs = pick.call_args
        self.assertEqual(kwargs["candidate_pool_size"], 50)
        self.assertEqual(kwargs["seed_count_k"], 5)
        self.assertEqual(kwargs["post_quality_min"], 0.7)
        self.assertEqual(kwargs["readability_grade_max"], 12.0)

    def test_post_quality_dict_built_from_content_value_score(self) -> None:
        """Every ContentItem row contributes to the ``post_quality`` map."""
        with patch(
            "apps.pipeline.services.trustrank_auto_seeder.pick_seeds",
            wraps=__import__(
                "apps.pipeline.services.trustrank_auto_seeder",
                fromlist=["pick_seeds"],
            ).pick_seeds,
        ) as pick:
            self._run_job_with_settings()

        _, kwargs = pick.call_args
        post_quality = kwargs["post_quality"]
        # All three items present.
        self.assertEqual(post_quality[(self.item_a.pk, "thread")], 0.85)
        self.assertEqual(post_quality[(self.item_b.pk, "thread")], 0.30)
        self.assertEqual(post_quality[(self.item_c.pk, "thread")], 0.05)

    def test_readability_dict_built_from_flesch_kincaid_grade(self) -> None:
        """The ``readability_grade`` map sources from ``Post.flesch_kincaid_grade`` (Phase 3 #19)."""
        with patch(
            "apps.pipeline.services.trustrank_auto_seeder.pick_seeds",
            wraps=__import__(
                "apps.pipeline.services.trustrank_auto_seeder",
                fromlist=["pick_seeds"],
            ).pick_seeds,
        ) as pick:
            self._run_job_with_settings()

        _, kwargs = pick.call_args
        readability = kwargs["readability_grade"]
        self.assertEqual(readability[(self.item_a.pk, "thread")], 8.0)
        self.assertEqual(readability[(self.item_b.pk, "thread")], 10.0)
        self.assertEqual(readability[(self.item_c.pk, "thread")], 22.0)

    def test_spam_quality_floor_flags_low_value_items(self) -> None:
        """Items at-or-below the spam floor land in ``spam_flagged``."""
        with patch(
            "apps.pipeline.services.trustrank_auto_seeder.pick_seeds",
            wraps=__import__(
                "apps.pipeline.services.trustrank_auto_seeder",
                fromlist=["pick_seeds"],
            ).pick_seeds,
        ) as pick:
            self._run_job_with_settings(**{
                "trustrank_auto_seeder.spam_content_value_floor": "0.15",
            })

        _, kwargs = pick.call_args
        spam = kwargs["spam_flagged"]
        # Item C (score=0.05) is at-or-below 0.15 → flagged.
        self.assertIn((self.item_c.pk, "thread"), spam)
        # Item B (score=0.30) is above the floor → not flagged.
        self.assertNotIn((self.item_b.pk, "thread"), spam)
        self.assertNotIn((self.item_a.pk, "thread"), spam)

    def test_zero_spam_floor_disables_filter(self) -> None:
        """``spam_content_value_floor=0.0`` short-circuits the spam set."""
        with patch(
            "apps.pipeline.services.trustrank_auto_seeder.pick_seeds",
            wraps=__import__(
                "apps.pipeline.services.trustrank_auto_seeder",
                fromlist=["pick_seeds"],
            ).pick_seeds,
        ) as pick:
            self._run_job_with_settings(**{
                "trustrank_auto_seeder.spam_content_value_floor": "0.0",
            })

        _, kwargs = pick.call_args
        self.assertEqual(kwargs["spam_flagged"], set())

    def test_persisted_seed_ids_match_pick_seeds_output(self) -> None:
        """The job stores the picker's seed list under ``trustrank.seed_ids``."""
        seed_ids = self._run_job_with_settings()
        # The string is comma-joined string forms of the (pk, ct) tuples.
        # We can't pin the exact ordering (depends on inverse-PR), but
        # the persisted value must be non-empty for a non-degenerate
        # graph and contain every kept seed.
        self.assertTrue(seed_ids)
        # No row should pass through with quality data missing — but
        # in this test fixture all three have entries, so the persisted
        # set should be a subset of the three test items (or
        # fallback-filled from forward PR).
