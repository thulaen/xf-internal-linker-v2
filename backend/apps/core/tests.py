from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APITestCase

from apps.core.models import AppSetting
from apps.suggestions.recommended_weights import recommended_bool, recommended_float, recommended_int
from apps.sync.models import SyncJob


@override_settings(WORDPRESS_BASE_URL="", WORDPRESS_USERNAME="", WORDPRESS_APP_PASSWORD="")
class WordPressSettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="settings-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_wordpress_settings_round_trip_and_schedule_task(self):
        response = self.client.put(
            "/api/settings/wordpress/",
            {
                "base_url": "https://blog.example.com/",
                "username": "editor",
                "app_password": "secret-token",
                "sync_enabled": True,
                "sync_hour": 4,
                "sync_minute": 15,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "base_url": "https://blog.example.com",
                "username": "editor",
                "app_password_configured": True,
                "sync_enabled": True,
                "sync_hour": 4,
                "sync_minute": 15,
            },
        )
        self.assertEqual(AppSetting.objects.get(key="wordpress.base_url").value, "https://blog.example.com")
        self.assertEqual(AppSetting.objects.get(key="wordpress.username").value, "editor")
        self.assertTrue(AppSetting.objects.get(key="wordpress.app_password").is_secret)

        periodic_task = PeriodicTask.objects.get(name="wordpress-content-sync")
        self.assertTrue(periodic_task.enabled)
        self.assertEqual(periodic_task.queue, "pipeline")
        self.assertIn('"source": "wp"', periodic_task.kwargs)

    def test_schedule_requires_base_url(self):
        response = self.client.put(
            "/api/settings/wordpress/",
            {
                "base_url": "",
                "username": "",
                "sync_enabled": True,
                "sync_hour": 3,
                "sync_minute": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("base_url", response.json()["detail"])

    @patch("apps.pipeline.tasks.dispatch_import_content")
    def test_manual_wordpress_sync_starts_sync_job(self, dispatch_import_mock):
        AppSetting.objects.create(
            key="wordpress.base_url",
            value="https://blog.example.com",
            value_type="str",
            category="sync",
            description="WordPress base URL",
        )

        response = self.client.post("/api/sync/wordpress/run/", {}, format="json")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        job = SyncJob.objects.get(job_id=payload["job_id"])
        self.assertEqual(job.source, "wp")
        self.assertEqual(job.mode, "full")
        dispatch_import_mock.assert_called_once()


@override_settings(WORDPRESS_BASE_URL="", WORDPRESS_USERNAME="", WORDPRESS_APP_PASSWORD="")
class WordPressSettingsDefaultsTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="defaults-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_defaults_expose_blank_public_configuration(self):
        response = self.client.get("/api/settings/wordpress/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "base_url": "",
                "username": "",
                "app_password_configured": False,
                "sync_enabled": False,
                "sync_hour": 3,
                "sync_minute": 0,
            },
        )


class WeightedAuthoritySettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="weighted-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_weighted_authority_defaults_and_round_trip(self):
        default_response = self.client.get("/api/settings/weighted-authority/")

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(
            default_response.json(),
            {
                "ranking_weight": recommended_float("weighted_authority.ranking_weight"),
                "position_bias": recommended_float("weighted_authority.position_bias"),
                "empty_anchor_factor": recommended_float("weighted_authority.empty_anchor_factor"),
                "bare_url_factor": recommended_float("weighted_authority.bare_url_factor"),
                "weak_context_factor": recommended_float("weighted_authority.weak_context_factor"),
                "isolated_context_factor": recommended_float("weighted_authority.isolated_context_factor"),
            },
        )

        update_response = self.client.put(
            "/api/settings/weighted-authority/",
            {
                "ranking_weight": 0.2,
                "position_bias": 0.25,
                "empty_anchor_factor": 0.7,
                "bare_url_factor": 0.4,
                "weak_context_factor": 0.8,
                "isolated_context_factor": 0.5,
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["ranking_weight"], 0.2)
        self.assertEqual(AppSetting.objects.get(key="weighted_authority.ranking_weight").value, "0.2")
        self.assertEqual(AppSetting.objects.get(key="weighted_authority.position_bias").value, "0.25")

    def test_weighted_authority_validation_rejects_bad_bounds(self):
        response = self.client.put(
            "/api/settings/weighted-authority/",
            {
                "ranking_weight": 0.3,
                "position_bias": 0.25,
                "empty_anchor_factor": 0.7,
                "bare_url_factor": 0.4,
                "weak_context_factor": 0.4,
                "isolated_context_factor": 0.5,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ranking_weight", response.json()["detail"])

    @patch("apps.pipeline.tasks.recalculate_weighted_authority.delay")
    def test_weighted_authority_recalculate_endpoint_returns_job(self, delay_mock):
        response = self.client.post("/api/settings/weighted-authority/recalculate/", {}, format="json")

        self.assertEqual(response.status_code, 202)
        self.assertIn("job_id", response.json())
        delay_mock.assert_called_once()


class LinkFreshnessSettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="freshness-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_link_freshness_defaults_and_round_trip(self):
        default_response = self.client.get("/api/settings/link-freshness/")

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(
            default_response.json(),
            {
                "ranking_weight": recommended_float("link_freshness.ranking_weight"),
                "recent_window_days": recommended_int("link_freshness.recent_window_days"),
                "newest_peer_percent": recommended_float("link_freshness.newest_peer_percent"),
                "min_peer_count": recommended_int("link_freshness.min_peer_count"),
                "w_recent": recommended_float("link_freshness.w_recent"),
                "w_growth": recommended_float("link_freshness.w_growth"),
                "w_cohort": recommended_float("link_freshness.w_cohort"),
                "w_loss": recommended_float("link_freshness.w_loss"),
            },
        )

        update_response = self.client.put(
            "/api/settings/link-freshness/",
            {
                "ranking_weight": 0.1,
                "recent_window_days": 45,
                "newest_peer_percent": 0.3,
                "min_peer_count": 4,
                "w_recent": 0.30,
                "w_growth": 0.30,
                "w_cohort": 0.25,
                "w_loss": 0.15,
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["ranking_weight"], 0.1)
        self.assertEqual(AppSetting.objects.get(key="link_freshness.ranking_weight").value, "0.1")
        self.assertEqual(AppSetting.objects.get(key="link_freshness.recent_window_days").value, "45")
        self.assertEqual(AppSetting.objects.get(key="link_freshness.ranking_weight").category, "link_freshness")

    def test_link_freshness_validation_rejects_bad_weights(self):
        response = self.client.put(
            "/api/settings/link-freshness/",
            {
                "ranking_weight": 0.1,
                "recent_window_days": 30,
                "newest_peer_percent": 0.25,
                "min_peer_count": 3,
                "w_recent": 0.2,
                "w_growth": 0.2,
                "w_cohort": 0.2,
                "w_loss": 0.2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("must equal 1.0", response.json()["detail"])

    @patch("apps.pipeline.tasks.recalculate_link_freshness.delay")
    def test_link_freshness_recalculate_endpoint_returns_job(self, delay_mock):
        response = self.client.post("/api/settings/link-freshness/recalculate/", {}, format="json")

        self.assertEqual(response.status_code, 202)
        self.assertIn("job_id", response.json())
        delay_mock.assert_called_once()


class PhraseMatchingSettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="phrase-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_phrase_matching_defaults_and_round_trip(self):
        default_response = self.client.get("/api/settings/phrase-matching/")

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(
            default_response.json(),
            {
                "ranking_weight": recommended_float("phrase_matching.ranking_weight"),
                "enable_anchor_expansion": recommended_bool("phrase_matching.enable_anchor_expansion"),
                "enable_partial_matching": recommended_bool("phrase_matching.enable_partial_matching"),
                "context_window_tokens": recommended_int("phrase_matching.context_window_tokens"),
            },
        )

        update_response = self.client.put(
            "/api/settings/phrase-matching/",
            {
                "ranking_weight": 0.05,
                "enable_anchor_expansion": False,
                "enable_partial_matching": False,
                "context_window_tokens": 10,
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["ranking_weight"], 0.05)
        self.assertFalse(update_response.json()["enable_anchor_expansion"])
        self.assertEqual(AppSetting.objects.get(key="phrase_matching.ranking_weight").value, "0.05")
        self.assertEqual(AppSetting.objects.get(key="phrase_matching.context_window_tokens").value, "10")
        self.assertEqual(AppSetting.objects.get(key="phrase_matching.ranking_weight").category, "anchor")

    def test_phrase_matching_validation_rejects_bad_bounds(self):
        response = self.client.put(
            "/api/settings/phrase-matching/",
            {
                "ranking_weight": 0.2,
                "enable_anchor_expansion": True,
                "enable_partial_matching": True,
                "context_window_tokens": 20,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ranking_weight", response.json()["detail"])


class LearnedAnchorSettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="learned-anchor-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_learned_anchor_defaults_and_round_trip(self):
        default_response = self.client.get("/api/settings/learned-anchor/")

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(
            default_response.json(),
            {
                "ranking_weight": recommended_float("learned_anchor.ranking_weight"),
                "minimum_anchor_sources": recommended_int("learned_anchor.minimum_anchor_sources"),
                "minimum_family_support_share": recommended_float("learned_anchor.minimum_family_support_share"),
                "enable_noise_filter": recommended_bool("learned_anchor.enable_noise_filter"),
            },
        )

        update_response = self.client.put(
            "/api/settings/learned-anchor/",
            {
                "ranking_weight": 0.04,
                "minimum_anchor_sources": 3,
                "minimum_family_support_share": 0.2,
                "enable_noise_filter": False,
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["ranking_weight"], 0.04)
        self.assertEqual(AppSetting.objects.get(key="learned_anchor.ranking_weight").value, "0.04")
        self.assertEqual(AppSetting.objects.get(key="learned_anchor.minimum_anchor_sources").value, "3")
        self.assertEqual(AppSetting.objects.get(key="learned_anchor.ranking_weight").category, "anchor")

    def test_learned_anchor_validation_rejects_bad_bounds(self):
        response = self.client.put(
            "/api/settings/learned-anchor/",
            {
                "ranking_weight": 0.2,
                "minimum_anchor_sources": 0,
                "minimum_family_support_share": 0.9,
                "enable_noise_filter": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ranking_weight", response.json()["detail"])


class RareTermPropagationSettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="rare-term-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_rare_term_propagation_defaults_and_round_trip(self):
        default_response = self.client.get("/api/settings/rare-term-propagation/")

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(
            default_response.json(),
            {
                "enabled": recommended_bool("rare_term_propagation.enabled"),
                "ranking_weight": recommended_float("rare_term_propagation.ranking_weight"),
                "max_document_frequency": recommended_int("rare_term_propagation.max_document_frequency"),
                "minimum_supporting_related_pages": recommended_int("rare_term_propagation.minimum_supporting_related_pages"),
            },
        )

        update_response = self.client.put(
            "/api/settings/rare-term-propagation/",
            {
                "enabled": False,
                "ranking_weight": 0.04,
                "max_document_frequency": 5,
                "minimum_supporting_related_pages": 3,
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertFalse(update_response.json()["enabled"])
        self.assertEqual(update_response.json()["ranking_weight"], 0.04)
        self.assertEqual(AppSetting.objects.get(key="rare_term_propagation.enabled").value, "false")
        self.assertEqual(AppSetting.objects.get(key="rare_term_propagation.max_document_frequency").value, "5")
        self.assertEqual(
            AppSetting.objects.get(key="rare_term_propagation.minimum_supporting_related_pages").value,
            "3",
        )
        self.assertEqual(AppSetting.objects.get(key="rare_term_propagation.ranking_weight").category, "ml")

    def test_rare_term_propagation_validation_rejects_bad_bounds(self):
        response = self.client.put(
            "/api/settings/rare-term-propagation/",
            {
                "enabled": True,
                "ranking_weight": 0.2,
                "max_document_frequency": 0,
                "minimum_supporting_related_pages": 6,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ranking_weight", response.json()["detail"])


class FieldAwareRelevanceSettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="field-aware-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_field_aware_relevance_defaults_and_round_trip(self):
        default_response = self.client.get("/api/settings/field-aware-relevance/")

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(
            default_response.json(),
            {
                "ranking_weight": recommended_float("field_aware_relevance.ranking_weight"),
                "title_field_weight": recommended_float("field_aware_relevance.title_field_weight"),
                "body_field_weight": recommended_float("field_aware_relevance.body_field_weight"),
                "scope_field_weight": recommended_float("field_aware_relevance.scope_field_weight"),
                "learned_anchor_field_weight": recommended_float("field_aware_relevance.learned_anchor_field_weight"),
            },
        )

        update_response = self.client.put(
            "/api/settings/field-aware-relevance/",
            {
                "ranking_weight": 0.05,
                "title_field_weight": 0.35,
                "body_field_weight": 0.35,
                "scope_field_weight": 0.15,
                "learned_anchor_field_weight": 0.15,
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["ranking_weight"], 0.05)
        self.assertEqual(AppSetting.objects.get(key="field_aware_relevance.ranking_weight").value, "0.05")
        self.assertEqual(AppSetting.objects.get(key="field_aware_relevance.body_field_weight").value, "0.35")
        self.assertEqual(AppSetting.objects.get(key="field_aware_relevance.ranking_weight").category, "ml")

    def test_field_aware_relevance_validation_rejects_bad_weights(self):
        response = self.client.put(
            "/api/settings/field-aware-relevance/",
            {
                "ranking_weight": 0.2,
                "title_field_weight": 0.4,
                "body_field_weight": 0.3,
                "scope_field_weight": 0.15,
                "learned_anchor_field_weight": 0.15,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ranking_weight", response.json()["detail"])

        response = self.client.put(
            "/api/settings/field-aware-relevance/",
            {
                "ranking_weight": 0.05,
                "title_field_weight": 0.4,
                "body_field_weight": 0.3,
                "scope_field_weight": 0.2,
                "learned_anchor_field_weight": 0.2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("must sum to 1.0", response.json()["detail"])
