from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APITestCase

from apps.analytics.models import AnalyticsSyncRun, SuggestionTelemetryDaily, TelemetryCoverageDaily
from apps.analytics.sync import run_ga4_sync, run_matomo_sync
from apps.core.models import AppSetting
from apps.content.models import ContentItem, Post, ScopeItem, Sentence, SiloGroup
from apps.suggestions.models import PipelineRun, Suggestion


class AnalyticsTelemetrySettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="analytics-user", password="pass")
        self.client.force_authenticate(user=user)

    def _build_suggestion(self, *, host_id: int = 101, destination_id: int = 202, title: str = "Destination Thread"):
        host = ContentItem.objects.create(
            content_id=host_id,
            content_type="thread",
            title=f"Host {host_id}",
            url=f"https://forum.example.com/host-{host_id}",
        )
        destination = ContentItem.objects.create(
            content_id=destination_id,
            content_type="thread",
            title=title,
            url=f"https://forum.example.com/destination-{destination_id}",
        )
        post = Post.objects.create(content_item=host, raw_bbcode="Body", clean_text="Host sentence")
        sentence = Sentence.objects.create(
            content_item=host,
            post=post,
            text="Host sentence",
            position=0,
            char_count=13,
            start_char=0,
            end_char=13,
            word_position=0,
        )
        pipeline_run = PipelineRun.objects.create(run_state="completed")
        return Suggestion.objects.create(
            pipeline_run=pipeline_run,
            destination=destination,
            destination_title=destination.title,
            host=host,
            host_sentence=sentence,
            host_sentence_text=sentence.text,
            anchor_phrase="host",
            anchor_start=0,
            anchor_end=4,
            anchor_confidence="strong",
        )

    def test_ga4_settings_round_trip_masks_secret_and_shared_values(self):
        response = self.client.put(
            "/api/analytics/settings/ga4/",
            {
                "behavior_enabled": True,
                "property_id": "123456789",
                "measurement_id": "G-TEST1234",
                "api_secret": "super-secret",
                "read_project_id": "ga4-read-project",
                "read_client_email": "reader@example.iam.gserviceaccount.com",
                "read_private_key": "-----BEGIN PRIVATE KEY-----\\nsecret\\n-----END PRIVATE KEY-----\\n",
                "sync_enabled": True,
                "sync_lookback_days": 9,
                "event_schema": "fr016_v1",
                "geo_granularity": "country",
                "retention_days": 365,
                "impression_visible_ratio": 0.6,
                "impression_min_ms": 1200,
                "engaged_min_seconds": 12,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["behavior_enabled"])
        self.assertEqual(payload["measurement_id"], "G-TEST1234")
        self.assertTrue(payload["api_secret_configured"])
        self.assertEqual(payload["read_project_id"], "ga4-read-project")
        self.assertEqual(payload["read_client_email"], "reader@example.iam.gserviceaccount.com")
        self.assertTrue(payload["read_private_key_configured"])
        self.assertEqual(payload["sync_lookback_days"], 9)
        self.assertEqual(AppSetting.objects.get(key="analytics.ga4_measurement_id").value, "G-TEST1234")
        self.assertTrue(AppSetting.objects.get(key="analytics.ga4_api_secret").is_secret)
        self.assertTrue(AppSetting.objects.get(key="analytics.ga4_read_private_key").is_secret)
        self.assertEqual(AppSetting.objects.get(key="analytics.telemetry_retention_days").value, "365")
        self.assertTrue(PeriodicTask.objects.get(name="analytics-ga4-telemetry-hourly-restatement").enabled)
        self.assertTrue(PeriodicTask.objects.get(name="analytics-ga4-telemetry-daily-catchup").enabled)

    @patch("apps.analytics.views.requests.post")
    def test_ga4_test_connection_uses_saved_secret(self, post_mock):
        AppSetting.objects.create(
            key="analytics.ga4_measurement_id",
            value="G-TEST1234",
            value_type="str",
            category="analytics",
            description="measurement id",
        )
        AppSetting.objects.create(
            key="analytics.ga4_api_secret",
            value="super-secret",
            value_type="str",
            category="analytics",
            description="api secret",
            is_secret=True,
        )
        post_mock.return_value.json.return_value = {"validationMessages": []}
        post_mock.return_value.raise_for_status.return_value = None

        response = self.client.post("/api/analytics/settings/ga4/test-connection/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "connected")
        post_mock.assert_called_once()

    @patch("apps.analytics.views.test_ga4_data_api_access")
    @patch("apps.analytics.views.build_ga4_data_service")
    def test_ga4_read_test_connection_uses_saved_read_credentials(self, build_mock, access_mock):
        AppSetting.objects.bulk_create(
            [
                AppSetting(
                    key="analytics.ga4_property_id",
                    value="123456789",
                    value_type="str",
                    category="analytics",
                    description="property id",
                ),
                AppSetting(
                    key="analytics.ga4_read_project_id",
                    value="ga4-read-project",
                    value_type="str",
                    category="analytics",
                    description="project id",
                ),
                AppSetting(
                    key="analytics.ga4_read_client_email",
                    value="reader@example.iam.gserviceaccount.com",
                    value_type="str",
                    category="analytics",
                    description="client email",
                ),
                AppSetting(
                    key="analytics.ga4_read_private_key",
                    value="-----BEGIN PRIVATE KEY-----\\nsecret\\n-----END PRIVATE KEY-----\\n",
                    value_type="str",
                    category="analytics",
                    description="private key",
                    is_secret=True,
                ),
            ]
        )
        build_mock.return_value = Mock()
        access_mock.return_value = {"rows": []}

        response = self.client.post("/api/analytics/settings/ga4/test-read-connection/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "connected")
        build_mock.assert_called_once()
        access_mock.assert_called_once()

    def test_matomo_settings_round_trip_masks_token(self):
        response = self.client.put(
            "/api/analytics/settings/matomo/",
            {
                "enabled": True,
                "url": "https://matomo.example.com/",
                "site_id_xenforo": "7",
                "site_id_wordpress": "9",
                "token_auth": "token-secret",
                "sync_enabled": True,
                "sync_lookback_days": 4,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["url"], "https://matomo.example.com")
        self.assertEqual(payload["site_id_xenforo"], "7")
        self.assertTrue(payload["token_auth_configured"])
        self.assertTrue(AppSetting.objects.get(key="analytics.matomo_token_auth").is_secret)

    @patch("apps.analytics.views.requests.get")
    def test_matomo_test_connection_returns_connected(self, get_mock):
        AppSetting.objects.create(
            key="analytics.matomo_url",
            value="https://matomo.example.com",
            value_type="str",
            category="analytics",
            description="matomo url",
        )
        AppSetting.objects.create(
            key="analytics.matomo_site_id_xenforo",
            value="7",
            value_type="str",
            category="analytics",
            description="site id",
        )
        AppSetting.objects.create(
            key="analytics.matomo_token_auth",
            value="token-secret",
            value_type="str",
            category="analytics",
            description="token",
            is_secret=True,
        )
        get_mock.return_value.json.return_value = {"idsite": 7, "name": "Forum"}
        get_mock.return_value.raise_for_status.return_value = None

        response = self.client.post("/api/analytics/settings/matomo/test-connection/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "connected")

    def test_overview_returns_last_sync_and_counts(self):
        AnalyticsSyncRun.objects.create(source="ga4", status="completed", rows_written=12, rows_updated=2, rows_read=20)
        response = self.client.get("/api/analytics/telemetry/overview/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ga4", payload)
        self.assertIn("matomo", payload)
        self.assertEqual(payload["telemetry_row_count"], 0)
        self.assertEqual(payload["coverage_row_count"], 0)

    def test_reporting_endpoints_return_funnel_trend_and_top_suggestions(self):
        suggestion = self._build_suggestion()
        SuggestionTelemetryDaily.objects.create(
            date=PipelineRun.objects.first().created_at.date(),
            telemetry_source="matomo",
            suggestion=suggestion,
            destination=suggestion.destination,
            host=suggestion.host,
            algorithm_key="pipeline_bundle",
            algorithm_version_slug="2026_04_02",
            event_schema="fr016_v1",
            source_label="xenforo",
            impressions=10,
            clicks=4,
            destination_views=3,
            engaged_sessions=2,
            conversions=1,
            sessions=3,
            event_count=20,
        )
        SuggestionTelemetryDaily.objects.create(
            date=PipelineRun.objects.first().created_at.date(),
            telemetry_source="ga4",
            suggestion=suggestion,
            destination=suggestion.destination,
            host=suggestion.host,
            algorithm_key="pipeline_bundle",
            algorithm_version_slug="2026_04_02",
            event_schema="fr016_v1",
            source_label="xenforo",
            device_category="desktop",
            default_channel_group="Organic Search",
            source_medium="google / organic",
            country="United Kingdom",
            impressions=5,
            clicks=2,
            destination_views=2,
            engaged_sessions=1,
            conversions=0,
            sessions=2,
            event_count=9,
        )

        funnel = self.client.get("/api/analytics/telemetry/funnel/?days=30")
        trend = self.client.get("/api/analytics/telemetry/trend/?days=30")
        top = self.client.get("/api/analytics/telemetry/top-suggestions/?days=30")

        self.assertEqual(funnel.status_code, 200)
        self.assertEqual(funnel.json()["totals"]["clicks"], 6)
        self.assertEqual(len(funnel.json()["by_source"]), 2)

        self.assertEqual(trend.status_code, 200)
        self.assertEqual(len(trend.json()["items"]), 1)
        self.assertEqual(trend.json()["items"][0]["ctr"], 0.4)

        self.assertEqual(top.status_code, 200)
        self.assertEqual(top.json()["items"][0]["destination_title"], "Destination Thread")
        self.assertEqual(top.json()["items"][0]["clicks"], 4)

    def test_health_endpoint_summarizes_coverage_by_source(self):
        TelemetryCoverageDaily.objects.create(
            date=PipelineRun.objects.create(run_state="completed").created_at.date(),
            event_schema="fr016_v1",
            source_label="ga4",
            expected_instrumented_links=10,
            observed_impression_links=8,
            observed_click_links=5,
            attributed_destination_sessions=7,
            unattributed_destination_sessions=3,
            duplicate_event_drops=2,
            missing_metadata_events=1,
            delayed_rows_rewritten=4,
            coverage_state="partial",
        )
        TelemetryCoverageDaily.objects.create(
            date=PipelineRun.objects.create(run_state="completed").created_at.date(),
            event_schema="fr016_v1",
            source_label="matomo",
            expected_instrumented_links=6,
            observed_impression_links=6,
            observed_click_links=4,
            attributed_destination_sessions=5,
            unattributed_destination_sessions=1,
            duplicate_event_drops=0,
            missing_metadata_events=0,
            delayed_rows_rewritten=1,
            coverage_state="healthy",
        )

        response = self.client.get("/api/analytics/telemetry/health/?days=30")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overall"]["row_count"], 2)
        self.assertEqual(payload["overall"]["healthy_days"], 1)
        self.assertEqual(payload["overall"]["partial_days"], 1)
        self.assertEqual(payload["overall"]["degraded_days"], 0)
        self.assertEqual(payload["overall"]["expected_instrumented_links"], 16)
        self.assertEqual(payload["overall"]["observed_impression_links"], 14)
        self.assertEqual(payload["overall"]["observed_click_links"], 9)
        self.assertEqual(payload["overall"]["attribution_rate"], 0.75)
        self.assertEqual(len(payload["sources"]), 2)
        self.assertEqual(payload["sources"][0]["source_label"], "ga4")
        self.assertEqual(payload["sources"][0]["impression_coverage_rate"], 0.8)
        self.assertEqual(payload["sources"][1]["source_label"], "matomo")
        self.assertEqual(payload["sources"][1]["latest_state"], "healthy")

    def test_breakdown_endpoint_returns_device_and_channel_rows(self):
        suggestion = self._build_suggestion()
        today = PipelineRun.objects.create(run_state="completed").created_at.date()
        SuggestionTelemetryDaily.objects.create(
            date=today,
            telemetry_source="ga4",
            suggestion=suggestion,
            destination=suggestion.destination,
            host=suggestion.host,
            algorithm_key="pipeline_bundle",
            algorithm_version_slug="2026_04_02",
            event_schema="fr016_v1",
            source_label="xenforo",
            device_category="mobile",
            default_channel_group="Organic Search",
            country="United Kingdom",
            impressions=12,
            clicks=5,
            engaged_sessions=3,
        )
        SuggestionTelemetryDaily.objects.create(
            date=today,
            telemetry_source="ga4",
            suggestion=suggestion,
            destination=suggestion.destination,
            host=suggestion.host,
            algorithm_key="pipeline_bundle",
            algorithm_version_slug="2026_04_02",
            event_schema="fr016_v1",
            source_label="xenforo",
            device_category="desktop",
            default_channel_group="Direct",
            country="United States",
            impressions=8,
            clicks=2,
            engaged_sessions=1,
        )

        response = self.client.get("/api/analytics/telemetry/breakdowns/?source=ga4&days=30")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected_source"], "ga4")
        self.assertEqual(payload["device_categories"][0]["label"], "mobile")
        self.assertEqual(payload["device_categories"][0]["clicks"], 5)
        self.assertEqual(payload["channel_groups"][0]["label"], "Organic Search")
        self.assertEqual(payload["channel_groups"][0]["ctr"], 0.4167)
        self.assertEqual(payload["countries"][0]["label"], "United Kingdom")
        self.assertEqual(payload["countries"][0]["clicks"], 5)

    def test_integration_view_returns_copy_ready_snippet_when_browser_events_enabled(self):
        AppSetting.objects.create(
            key="analytics.ga4_behavior_enabled",
            value="true",
            value_type="bool",
            category="analytics",
            description="enabled",
        )
        AppSetting.objects.create(
            key="analytics.ga4_measurement_id",
            value="G-TEST1234",
            value_type="str",
            category="analytics",
            description="measurement",
        )

        response = self.client.get("/api/analytics/telemetry/integration/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["ga4_browser_ready"])
        self.assertIn("suggestion_link_impression", payload["browser_snippet"])
        self.assertIn("sessionStorage", payload["browser_snippet"])
        self.assertNotIn("anchor_phrase", payload["browser_snippet"])

    def test_integration_view_explains_when_settings_are_missing(self):
        response = self.client.get("/api/analytics/telemetry/integration/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "needs_settings")
        self.assertFalse(payload["ga4_browser_ready"])
        self.assertFalse(payload["matomo_browser_ready"])

    @patch("apps.analytics.views.sync_matomo_telemetry.delay")
    def test_matomo_sync_endpoint_queues_task(self, delay_mock):
        delay_mock.return_value = Mock(id="matomo-task-1")
        AppSetting.objects.create(
            key="analytics.matomo_sync_lookback_days",
            value="4",
            value_type="int",
            category="analytics",
            description="lookback",
        )

        response = self.client.post("/api/analytics/telemetry/matomo-sync/", {}, format="json")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["source"], "matomo")
        delay_mock.assert_called_once()
        sync_run = AnalyticsSyncRun.objects.get(pk=payload["sync_run_id"])
        self.assertEqual(sync_run.source, "matomo")
        self.assertEqual(sync_run.lookback_days, 4)

    @patch("apps.analytics.views.sync_ga4_telemetry.delay")
    def test_ga4_sync_endpoint_queues_task(self, delay_mock):
        delay_mock.return_value = Mock(id="ga4-task-1")
        AppSetting.objects.create(
            key="analytics.ga4_sync_lookback_days",
            value="6",
            value_type="int",
            category="analytics",
            description="lookback",
        )

        response = self.client.post("/api/analytics/telemetry/ga4-sync/", {}, format="json")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["source"], "ga4")
        delay_mock.assert_called_once()
        sync_run = AnalyticsSyncRun.objects.get(pk=payload["sync_run_id"])
        self.assertEqual(sync_run.source, "ga4")
        self.assertEqual(sync_run.lookback_days, 6)

    @patch("apps.analytics.sync.requests.get")
    def test_run_matomo_sync_writes_daily_rollups(self, get_mock):
        AppSetting.objects.bulk_create(
            [
                AppSetting(
                    key="analytics.matomo_enabled",
                    value="true",
                    value_type="bool",
                    category="analytics",
                    description="enabled",
                ),
                AppSetting(
                    key="analytics.matomo_url",
                    value="https://matomo.example.com",
                    value_type="str",
                    category="analytics",
                    description="url",
                ),
                AppSetting(
                    key="analytics.matomo_site_id_xenforo",
                    value="7",
                    value_type="str",
                    category="analytics",
                    description="site id",
                ),
                AppSetting(
                    key="analytics.matomo_token_auth",
                    value="token-secret",
                    value_type="str",
                    category="analytics",
                    description="token",
                    is_secret=True,
                ),
                AppSetting(
                    key="analytics.matomo_sync_enabled",
                    value="true",
                    value_type="bool",
                    category="analytics",
                    description="sync enabled",
                ),
                AppSetting(
                    key="analytics.telemetry_event_schema",
                    value="fr016_v1",
                    value_type="str",
                    category="analytics",
                    description="schema",
                ),
            ]
        )

        silo = SiloGroup.objects.create(name="Music", slug="music")
        host_scope = ScopeItem.objects.create(scope_id=11, scope_type="node", title="Host", silo_group=silo)
        destination_scope = ScopeItem.objects.create(scope_id=12, scope_type="node", title="Destination", silo_group=silo)
        host = ContentItem.objects.create(
            content_id=101,
            content_type="thread",
            title="Host Thread",
            url="https://forum.example.com/host-thread",
            scope=host_scope,
        )
        destination = ContentItem.objects.create(
            content_id=202,
            content_type="thread",
            title="Destination Thread",
            url="https://forum.example.com/destination-thread",
            scope=destination_scope,
        )
        post = Post.objects.create(content_item=host, raw_bbcode="Test body", clean_text="Helpful host sentence.")
        sentence = Sentence.objects.create(
            content_item=host,
            post=post,
            text="Helpful host sentence.",
            position=0,
            char_count=21,
            start_char=0,
            end_char=21,
            word_position=0,
        )
        pipeline_run = PipelineRun.objects.create(run_state="completed")
        suggestion = Suggestion.objects.create(
            pipeline_run=pipeline_run,
            destination=destination,
            destination_title=destination.title,
            host=host,
            host_sentence=sentence,
            host_sentence_text=sentence.text,
            anchor_phrase="helpful",
            anchor_start=0,
            anchor_end=7,
            anchor_confidence="strong",
        )
        sync_run = AnalyticsSyncRun.objects.create(source="matomo", status="pending", lookback_days=1)

        get_mock.return_value.json.return_value = [
            {
                "label": "suggestion_link_impression",
                "subtable": [
                    {"label": str(suggestion.suggestion_id), "nb_events": 3},
                ],
            },
            {
                "label": "suggestion_link_click",
                "subtable": [
                    {"label": str(suggestion.suggestion_id), "nb_events": 2},
                ],
            },
            {
                "label": "suggestion_destination_view",
                "subtable": [
                    {"label": str(suggestion.suggestion_id), "nb_events": 5},
                ],
            },
        ]
        get_mock.return_value.raise_for_status.return_value = None

        stats = run_matomo_sync(sync_run)

        self.assertEqual(stats["rows_written"], 1)
        self.assertEqual(stats["rows_updated"], 0)
        telemetry_row = SuggestionTelemetryDaily.objects.get()
        self.assertEqual(telemetry_row.telemetry_source, "matomo")
        self.assertEqual(telemetry_row.suggestion_id, suggestion.suggestion_id)
        self.assertEqual(telemetry_row.impressions, 3)
        self.assertEqual(telemetry_row.clicks, 2)
        self.assertEqual(telemetry_row.destination_views, 5)
        self.assertEqual(telemetry_row.event_count, 10)
        self.assertEqual(telemetry_row.event_schema, "fr016_v1")
        coverage_row = TelemetryCoverageDaily.objects.get()
        self.assertEqual(coverage_row.source_label, "matomo")
        self.assertEqual(coverage_row.observed_impression_links, 1)
        self.assertEqual(coverage_row.observed_click_links, 1)
        self.assertEqual(coverage_row.attributed_destination_sessions, 5)

    @patch("apps.analytics.sync.build_ga4_data_service")
    def test_run_ga4_sync_writes_daily_rollups(self, build_service_mock):
        AppSetting.objects.bulk_create(
            [
                AppSetting(
                    key="analytics.ga4_sync_enabled",
                    value="true",
                    value_type="bool",
                    category="analytics",
                    description="sync enabled",
                ),
                AppSetting(
                    key="analytics.ga4_property_id",
                    value="123456789",
                    value_type="str",
                    category="analytics",
                    description="property id",
                ),
                AppSetting(
                    key="analytics.ga4_read_project_id",
                    value="ga4-read-project",
                    value_type="str",
                    category="analytics",
                    description="read project id",
                ),
                AppSetting(
                    key="analytics.ga4_read_client_email",
                    value="reader@example.iam.gserviceaccount.com",
                    value_type="str",
                    category="analytics",
                    description="read client email",
                ),
                AppSetting(
                    key="analytics.ga4_read_private_key",
                    value="-----BEGIN PRIVATE KEY-----\\nsecret\\n-----END PRIVATE KEY-----\\n",
                    value_type="str",
                    category="analytics",
                    description="read private key",
                    is_secret=True,
                ),
            ]
        )
        host = ContentItem.objects.create(
            content_id=301,
            content_type="thread",
            title="Host Thread",
            url="https://forum.example.com/host-thread",
        )
        destination = ContentItem.objects.create(
            content_id=302,
            content_type="thread",
            title="Destination Thread",
            url="https://forum.example.com/destination-thread",
        )
        post = Post.objects.create(content_item=host, raw_bbcode="Body", clean_text="Host sentence")
        sentence = Sentence.objects.create(
            content_item=host,
            post=post,
            text="Host sentence",
            position=0,
            char_count=13,
            start_char=0,
            end_char=13,
            word_position=0,
        )
        pipeline_run = PipelineRun.objects.create(run_state="completed")
        suggestion = Suggestion.objects.create(
            pipeline_run=pipeline_run,
            destination=destination,
            destination_title=destination.title,
            host=host,
            host_sentence=sentence,
            host_sentence_text=sentence.text,
            anchor_phrase="host",
            anchor_start=0,
            anchor_end=4,
            anchor_confidence="strong",
        )
        sync_run = AnalyticsSyncRun.objects.create(source="ga4", status="pending", lookback_days=1)
        service = Mock()
        build_service_mock.return_value = service
        service.properties.return_value.runReport.return_value.execute.side_effect = [
            {
                "rows": [
                    {
                        "dimensionValues": [
                            {"value": sync_run.started_at.date().strftime("%Y%m%d")},
                            {"value": str(suggestion.suggestion_id)},
                            {"value": "desktop"},
                            {"value": "Organic Search"},
                            {"value": "google / organic"},
                            {"value": "United Kingdom"},
                        ],
                        "metricValues": [{"value": "3"}],
                    }
                ]
            },
            {
                "rows": [
                    {
                        "dimensionValues": [
                            {"value": sync_run.started_at.date().strftime("%Y%m%d")},
                            {"value": str(suggestion.suggestion_id)},
                            {"value": "desktop"},
                            {"value": "Organic Search"},
                            {"value": "google / organic"},
                            {"value": "United Kingdom"},
                        ],
                        "metricValues": [{"value": "2"}],
                    }
                ]
            },
            {"rows": []},
            {"rows": []},
            {
                "rows": [
                    {
                        "dimensionValues": [
                            {"value": sync_run.started_at.date().strftime("%Y%m%d")},
                            {"value": str(suggestion.suggestion_id)},
                            {"value": "desktop"},
                            {"value": "Organic Search"},
                            {"value": "google / organic"},
                            {"value": "United Kingdom"},
                        ],
                        "metricValues": [
                            {"value": "5"},
                            {"value": "5"},
                            {"value": "4"},
                            {"value": "40"},
                        ],
                    }
                ]
            },
        ]

        stats = run_ga4_sync(sync_run)

        self.assertEqual(stats["rows_written"], 1)
        telemetry_row = SuggestionTelemetryDaily.objects.get(telemetry_source="ga4")
        self.assertEqual(telemetry_row.suggestion_id, suggestion.suggestion_id)
        self.assertEqual(telemetry_row.impressions, 3)
        self.assertEqual(telemetry_row.clicks, 2)
        self.assertEqual(telemetry_row.destination_views, 5)
        self.assertEqual(telemetry_row.sessions, 5)
        self.assertEqual(telemetry_row.engaged_sessions, 4)
        self.assertEqual(telemetry_row.total_engagement_time_seconds, 40.0)
        coverage_row = TelemetryCoverageDaily.objects.get(source_label="ga4")
        self.assertEqual(coverage_row.observed_impression_links, 1)
        self.assertEqual(coverage_row.observed_click_links, 1)
        self.assertEqual(coverage_row.attributed_destination_sessions, 5)
class GSCSlice1Tests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="gsc-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_gsc_settings_round_trip(self):
        """Verify that GSC settings can be saved and retrieved accurately."""
        response = self.client.put(
            "/api/analytics/settings/gsc/",
            {
                "property_url": "sc-domain:example.com",
                "client_email": "gsc-bot@example.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE-KEY\\n-----END PRIVATE KEY-----\\n",
                "sync_enabled": True,
                "sync_lookback_days": 14,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["property_url"], "sc-domain:example.com")
        self.assertTrue(payload["private_key_configured"])
        
        # Verify DB persistence
        self.assertEqual(AppSetting.objects.get(key="analytics.gsc_property_url").value, "sc-domain:example.com")
        self.assertTrue(AppSetting.objects.get(key="analytics.gsc_private_key").is_secret)

    def test_gsc_models_persistence(self):
        """Verify that the new GSCDailyPerformance and GSCImpactSnapshot models function."""
        from apps.analytics.models import GSCDailyPerformance, GSCImpactSnapshot
        from django.utils import timezone
        
        # Create raw performance data
        perf = GSCDailyPerformance.objects.create(
            page_url="https://example.com/page-1",
            date=timezone.now().date(),
            impressions=1000,
            clicks=50,
            avg_position=12.5,
            ctr=0.05,
            property_url="sc-domain:example.com"
        )
        self.assertEqual(GSCDailyPerformance.objects.count(), 1)
        
        # Create impact snapshot (requires a suggestion)
        host = ContentItem.objects.create(content_id=501, title="Host")
        dest = ContentItem.objects.create(content_id=502, title="Dest")
        post = Post.objects.create(content_item=host, clean_text="Host sentence")
        sentence = Sentence.objects.create(
            content_item=host, post=post, text="Host sentence",
            position=0, char_count=13, start_char=0, end_char=13, word_position=0
        )
        suggestion = Suggestion.objects.create(
            destination=dest, host=host, host_sentence=sentence,
            status="applied", applied_at=timezone.now()
        )
        
        impact = GSCImpactSnapshot.objects.create(
            suggestion=suggestion,
            apply_date=timezone.now(),
            window_type="28d",
            baseline_clicks=10,
            post_clicks=20,
            lift_clicks_pct=1.0,
            lift_clicks_absolute=10,
            probability_of_uplift=0.99,
            reward_label="positive"
        )
        self.assertEqual(GSCImpactSnapshot.objects.count(), 1)
        self.assertEqual(suggestion.gsc_impacts.first().reward_label, "positive")



class GSCSlice3Tests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="gsc-ingest", password="pass")
        self.client.force_authenticate(user=user)
        
        # Setup settings
        AppSetting.objects.bulk_create([
            AppSetting(key="analytics.gsc_sync_enabled", value="true", value_type="bool", category="analytics"),
            AppSetting(key="analytics.gsc_property_url", value="https://example.com/", value_type="str", category="analytics"),
            AppSetting(key="analytics.gsc_client_email", value="bot@example.com", value_type="str", category="analytics"),
            AppSetting(key="analytics.gsc_private_key", value="-----BEGIN PRIVATE KEY-----\nKEY\n-----END PRIVATE KEY-----", value_type="str", category="analytics", is_secret=True),
        ])
        
        # Setup ContentItem for legacy mapping test
        self.item = ContentItem.objects.create(
            content_id=601,
            title="Ingested Page",
            url="https://example.com/ingested-page",
        )

    @patch("apps.analytics.gsc_client.build_gsc_service")
    @patch("apps.analytics.gsc_client.fetch_gsc_performance_data")
    def test_run_gsc_sync_populates_models(self, fetch_mock, build_mock):
        from apps.analytics.sync import run_gsc_sync
        from apps.analytics.models import GSCDailyPerformance, SearchMetric, AnalyticsSyncRun
        from django.utils import timezone
        
        # Mock GSC Response (page-level total)
        fetch_mock.return_value = [
            {
                "keys": ["2026-04-01", "https://example.com/ingested-page"],
                "clicks": 10,
                "impressions": 100,
                "ctr": 0.1,
                "position": 5.5
            },
            {
                "keys": ["2026-04-01", "https://example.com/untracked-page"],
                "clicks": 5,
                "impressions": 50,
                "ctr": 0.1,
                "position": 10.0
            }
        ]
        
        sync_run = AnalyticsSyncRun.objects.create(source="gsc", lookback_days=7)
        stats = run_gsc_sync(sync_run)
        
        self.assertEqual(stats["rows_read"], 2)
        self.assertEqual(stats["rows_written"], 2)
        
        # Verify GSCDailyPerformance (both pages)
        self.assertEqual(GSCDailyPerformance.objects.count(), 2)
        perf_tracked = GSCDailyPerformance.objects.get(page_url="https://example.com/ingested-page")
        self.assertEqual(perf_tracked.clicks, 10)
        
        # Verify SearchMetric (only the tracked page)
        self.assertEqual(SearchMetric.objects.count(), 1)
        metric = SearchMetric.objects.get(content_item=self.item)
        self.assertEqual(metric.clicks, 10)
        self.assertEqual(metric.source, "gsc")

    @patch("apps.analytics.gsc_client.build_gsc_service")
    @patch("apps.analytics.gsc_client.fetch_gsc_performance_data")
    def test_run_gsc_sync_updates_existing_rows(self, fetch_mock, build_mock):
        from apps.analytics.sync import run_gsc_sync
        from apps.analytics.models import GSCDailyPerformance, AnalyticsSyncRun
        
        # Pre-create a row
        GSCDailyPerformance.objects.create(
            page_url="https://example.com/ingested-page",
            date="2026-04-01",
            property_url="https://example.com/",
            clicks=1,
            impressions=10
        )
        
        fetch_mock.return_value = [
            {
                "keys": ["2026-04-01", "https://example.com/ingested-page"],
                "clicks": 10,
                "impressions": 100,
                "ctr": 0.1,
                "position": 5.5
            }
        ]
        
        sync_run = AnalyticsSyncRun.objects.create(source="gsc", lookback_days=1)
        stats = run_gsc_sync(sync_run)
        
        self.assertEqual(stats["rows_read"], 1)
        self.assertEqual(stats["rows_updated"], 1)
        
        perf = GSCDailyPerformance.objects.get(page_url="https://example.com/ingested-page")
        self.assertEqual(perf.clicks, 10) # Updated from 1 to 10
