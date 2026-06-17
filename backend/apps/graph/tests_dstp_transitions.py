from __future__ import annotations

from datetime import date, datetime, timezone

from django.test import SimpleTestCase, TestCase

from apps.content.models import ContentItem, ScopeItem
from apps.graph.api import current_dstp_transitions
from apps.graph.models import DirectionalTransitionEdge
from apps.graph.services.dstp_transitions import (
    AnalyticsTransitionObservation,
    ga4_page_rows_to_transition_observations,
    matomo_visits_to_transition_counts,
    matomo_visits_to_transition_observations,
    normalize_analytics_path,
    observations_to_deduped_transition_counts,
    upsert_directional_transition_edges,
)


class DSTPMatomoParsingTests(SimpleTestCase):
    def test_ordered_matomo_visit_builds_immediate_transition(self):
        visits = [
            {
                "actionDetails": [
                    {"type": "action", "url": "https://goldmidi.com/community/a/"},
                    {"type": "action", "url": "https://goldmidi.com/community/a/?x=1"},
                    {"type": "action", "url": "https://goldmidi.com/community/b/"},
                    {"type": "event", "url": "https://goldmidi.com/community/c/"},
                ]
            }
        ]
        path_to_id = {
            "/community/a": 11,
            "/community/b": 22,
            "/community/c": 33,
        }

        result = matomo_visits_to_transition_counts(visits, path_to_id)

        self.assertEqual(result.transition_counts, {(11, 22): 1})
        self.assertEqual(result.out_degrees, {11: 1})
        self.assertEqual(result.visits_processed, 1)

    def test_normalize_analytics_path_strips_query_and_trailing_slash(self):
        self.assertEqual(
            normalize_analytics_path("https://goldmidi.com/community/a/?x=1"),
            "/community/a",
        )

    def test_deduped_counts_take_one_cross_source_transition(self):
        happened_at = datetime(2026, 6, 16, 10, 30, tzinfo=timezone.utc)
        observations = [
            AnalyticsTransitionObservation(
                source="matomo",
                site_id="3",
                source_content_id=11,
                dest_content_id=22,
                occurred_at=happened_at,
                count=2,
            ),
            AnalyticsTransitionObservation(
                source="ga4",
                site_id="3",
                source_content_id=11,
                dest_content_id=22,
                occurred_at=happened_at,
                count=3,
            ),
        ]

        result = observations_to_deduped_transition_counts(observations)

        self.assertEqual(result.transition_counts, {(11, 22): 3})
        self.assertEqual(result.out_degrees, {11: 3})

    def test_shared_first_party_visit_id_dedupes_across_minutes(self):
        observations = [
            AnalyticsTransitionObservation(
                source="matomo",
                site_id="3",
                source_content_id=11,
                dest_content_id=22,
                occurred_at=datetime(2026, 6, 16, 10, 30, tzinfo=timezone.utc),
                count=1,
                visit_id="xfil-visit-123",
            ),
            AnalyticsTransitionObservation(
                source="ga4",
                site_id="3",
                source_content_id=11,
                dest_content_id=22,
                occurred_at=datetime(2026, 6, 16, 10, 31, tzinfo=timezone.utc),
                count=1,
                visit_id="xfil-visit-123",
            ),
        ]

        result = observations_to_deduped_transition_counts(observations)

        self.assertEqual(result.transition_counts, {(11, 22): 1})
        self.assertEqual(result.out_degrees, {11: 1})

    def test_matomo_visits_build_transition_observations_with_action_time(self):
        visits = [
            {
                "xfil_visit_id": "xfil-visit-abc",
                "actionDetails": [
                    {
                        "type": "action",
                        "url": "https://goldmidi.com/community/a/",
                        "timestamp": "2026-06-16T10:30:05+00:00",
                    },
                    {
                        "type": "action",
                        "url": "https://goldmidi.com/community/b/",
                        "timestamp": "2026-06-16T10:30:30+00:00",
                    },
                ]
            }
        ]

        observations = matomo_visits_to_transition_observations(
            visits,
            {"/community/a": 11, "/community/b": 22},
            site_id="3",
        )

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].source_content_id, 11)
        self.assertEqual(observations[0].dest_content_id, 22)
        self.assertEqual(observations[0].occurred_at.minute, 30)
        self.assertEqual(observations[0].visit_id, "xfil-visit-abc")

    def test_ga4_rows_build_transition_observations_from_referrer(self):
        rows = [
            {
                "dimensionValues": [
                    {"value": "202606161030"},
                    {"value": "https://goldmidi.com/community/a/"},
                    {"value": "https://goldmidi.com/community/b/"},
                    {"value": "xfil-visit-def"},
                ],
                "metricValues": [{"value": "4"}],
            }
        ]

        observations = ga4_page_rows_to_transition_observations(
            rows,
            {"/community/a": 11, "/community/b": 22},
            site_id="3",
        )

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].source, "ga4")
        self.assertEqual(observations[0].source_content_id, 11)
        self.assertEqual(observations[0].dest_content_id, 22)
        self.assertEqual(observations[0].count, 4)
        self.assertEqual(observations[0].visit_id, "xfil-visit-def")


class DSTPTransitionStorageTests(TestCase):
    def setUp(self):
        self.scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Scope")
        self.source = ContentItem.objects.create(
            content_id=101,
            content_type="thread",
            title="Source",
            scope=self.scope,
            url="https://goldmidi.com/community/source/",
        )
        self.destination = ContentItem.objects.create(
            content_id=202,
            content_type="thread",
            title="Destination",
            scope=self.scope,
            url="https://goldmidi.com/community/destination/",
        )

    def test_upsert_replaces_existing_pair_without_duplicate_rows(self):
        window_start = date(2026, 6, 1)
        window_end = date(2026, 6, 16)

        first = upsert_directional_transition_edges(
            source="matomo",
            site_id="3",
            transition_counts={(self.source.pk, self.destination.pk): 2},
            out_degrees={self.source.pk: 3},
            window_start=window_start,
            window_end=window_end,
        )
        second = upsert_directional_transition_edges(
            source="matomo",
            site_id="3",
            transition_counts={(self.source.pk, self.destination.pk): 5},
            out_degrees={self.source.pk: 8},
            window_start=window_start,
            window_end=window_end,
        )

        self.assertEqual(first, 1)
        self.assertEqual(second, 1)
        self.assertEqual(DirectionalTransitionEdge.objects.count(), 1)
        edge = DirectionalTransitionEdge.objects.get()
        self.assertEqual(edge.transition_count, 5)
        self.assertEqual(edge.source_transition_count, 8)

    def test_upsert_prunes_pair_missing_from_latest_matomo_window(self):
        other_destination = ContentItem.objects.create(
            content_id=303,
            content_type="thread",
            title="Other destination",
            scope=self.scope,
            url="https://goldmidi.com/community/other-destination/",
        )
        window_start = date(2026, 6, 1)
        window_end = date(2026, 6, 16)

        upsert_directional_transition_edges(
            source="matomo",
            site_id="3",
            transition_counts={
                (self.source.pk, self.destination.pk): 2,
                (self.source.pk, other_destination.pk): 1,
            },
            out_degrees={self.source.pk: 3},
            window_start=window_start,
            window_end=window_end,
        )
        upsert_directional_transition_edges(
            source="matomo",
            site_id="3",
            transition_counts={(self.source.pk, self.destination.pk): 4},
            out_degrees={self.source.pk: 4},
            window_start=window_start,
            window_end=window_end,
        )

        self.assertFalse(
            DirectionalTransitionEdge.objects.filter(
                source_content_item=self.source,
                dest_content_item=other_destination,
            ).exists()
        )
        edge = DirectionalTransitionEdge.objects.get(
            source_content_item=self.source,
            dest_content_item=self.destination,
        )
        self.assertEqual(edge.transition_count, 4)

    def test_current_dstp_transitions_returns_content_keys(self):
        upsert_directional_transition_edges(
            source="matomo",
            site_id="3",
            transition_counts={(self.source.pk, self.destination.pk): 4},
            out_degrees={self.source.pk: 6},
            window_start=date(2026, 6, 1),
            window_end=date(2026, 6, 16),
        )

        transition_counts, out_degrees = current_dstp_transitions()

        source_key = (self.source.pk, self.source.content_type)
        destination_key = (self.destination.pk, self.destination.content_type)
        self.assertEqual(transition_counts[(source_key, destination_key)], 4)
        self.assertEqual(out_degrees[source_key], 6)

    def test_current_dstp_transitions_prefers_combined_rows(self):
        upsert_directional_transition_edges(
            source="matomo",
            site_id="3",
            transition_counts={(self.source.pk, self.destination.pk): 4},
            out_degrees={self.source.pk: 4},
            window_start=date(2026, 6, 1),
            window_end=date(2026, 6, 16),
        )
        upsert_directional_transition_edges(
            source="combined",
            site_id="3",
            transition_counts={(self.source.pk, self.destination.pk): 7},
            out_degrees={self.source.pk: 7},
            window_start=date(2026, 6, 1),
            window_end=date(2026, 6, 16),
        )

        transition_counts, out_degrees = current_dstp_transitions()

        source_key = (self.source.pk, self.source.content_type)
        destination_key = (self.destination.pk, self.destination.content_type)
        self.assertEqual(transition_counts[(source_key, destination_key)], 7)
        self.assertEqual(out_degrees[source_key], 7)
