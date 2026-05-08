"""Tests for the pure-function helpers extracted from analytics/views.py.

These helpers replaced ~600 lines of inlined try/except/dict-literal
boilerplate across 14 long functions. Each is independently testable in
``SimpleTestCase`` (no DB) so a future tweak to wording or threshold
shows up here before it ships.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.analytics.views import (
    _format_breakdown_rows,
    _format_setting_value,
    _format_top_suggestion_row,
    _ga4_browser_status,
    _ga4_periodic_enabled,
    _ga4_read_status,
    _gsc_connection_status,
    _gsc_periodic_enabled,
    _matomo_periodic_enabled,
    _resolve_matomo_test_credentials,
    _validate_oauth_callback_inputs,
)


class FormatSettingValueTests(SimpleTestCase):
    """The bool↔string adapter used by every persist-spec table."""

    def test_bool_true(self):
        self.assertEqual(_format_setting_value(True, "bool"), "true")

    def test_bool_false(self):
        self.assertEqual(_format_setting_value(False, "bool"), "false")

    def test_int_passthrough(self):
        self.assertEqual(_format_setting_value(42, "int"), "42")

    def test_str_passthrough(self):
        self.assertEqual(_format_setting_value("abc", "str"), "abc")

    def test_float_passthrough(self):
        self.assertEqual(_format_setting_value(0.5, "float"), "0.5")


class GA4BrowserStatusTests(SimpleTestCase):
    """Browser-event status card wording."""

    def test_both_creds_saved(self):
        status, message = _ga4_browser_status("G-ABC123", "secret")
        self.assertEqual(status, "saved")
        self.assertIn("Run Test Connection", message)

    def test_neither_set(self):
        status, message = _ga4_browser_status("", "")
        self.assertEqual(status, "not_configured")
        self.assertIn("test the connection", message)

    def test_only_measurement_id(self):
        status, _ = _ga4_browser_status("G-ABC", "")
        self.assertEqual(status, "not_configured")

    def test_only_secret(self):
        status, _ = _ga4_browser_status("", "secret")
        self.assertEqual(status, "not_configured")


class GA4ReadStatusTests(SimpleTestCase):
    """Read-access status card priority: sync result > oauth > saved-creds > none."""

    def test_completed_sync_wins(self):
        status, _ = _ga4_read_status(
            oauth_connected=True,
            property_id="123",
            read_client_email="x@y.iam",
            read_private_key="key",
            sync={"status": "completed"},
        )
        self.assertEqual(status, "connected")

    def test_failed_sync_returns_error(self):
        status, message = _ga4_read_status(
            oauth_connected=True,
            property_id="123",
            read_client_email="x@y.iam",
            read_private_key="key",
            sync={"status": "failed", "error_message": "boom"},
        )
        self.assertEqual(status, "error")
        self.assertEqual(message, "boom")

    def test_oauth_connected_no_sync(self):
        status, _ = _ga4_read_status(
            oauth_connected=True,
            property_id="123",
            read_client_email="",
            read_private_key="",
            sync=None,
        )
        self.assertEqual(status, "connected")

    def test_service_account_creds_saved(self):
        status, _ = _ga4_read_status(
            oauth_connected=False,
            property_id="123",
            read_client_email="x@y.iam",
            read_private_key="key",
            sync=None,
        )
        self.assertEqual(status, "saved")

    def test_nothing_configured(self):
        status, message = _ga4_read_status(
            oauth_connected=False,
            property_id="",
            read_client_email="",
            read_private_key="",
            sync=None,
        )
        self.assertEqual(status, "not_configured")
        self.assertIn("Connect Google", message)


class GSCConnectionStatusTests(SimpleTestCase):
    """GSC settings card: same priority pattern as GA4 read."""

    def test_completed_sync_wins(self):
        status, _ = _gsc_connection_status(
            oauth_connected=True,
            property_url="https://example.com/",
            client_email="",
            private_key="",
            sync={"status": "completed"},
        )
        self.assertEqual(status, "connected")

    def test_oauth_connected_with_property(self):
        status, message = _gsc_connection_status(
            oauth_connected=True,
            property_url="https://example.com/",
            client_email="",
            private_key="",
            sync=None,
        )
        self.assertEqual(status, "connected")
        self.assertEqual(message, "Connected to Google.")

    def test_oauth_connected_no_property_yet(self):
        status, message = _gsc_connection_status(
            oauth_connected=True,
            property_url="",
            client_email="",
            private_key="",
            sync=None,
        )
        self.assertEqual(status, "saved")
        self.assertIn("Add the Search Console property URL", message)

    def test_service_account_creds(self):
        status, _ = _gsc_connection_status(
            oauth_connected=False,
            property_url="https://example.com/",
            client_email="x@y.iam",
            private_key="key",
            sync=None,
        )
        self.assertEqual(status, "saved")


class PeriodicEnabledTruthTablesTests(SimpleTestCase):
    """Each ``_*_periodic_enabled`` helper requires every checked field truthy."""

    def test_ga4_all_truthy_passes(self):
        self.assertTrue(
            _ga4_periodic_enabled(
                {
                    "sync_enabled": True,
                    "property_id": "123",
                    "read_project_id": "p",
                    "read_client_email": "x@y.iam",
                    "read_private_key_configured": True,
                }
            )
        )

    def test_ga4_one_falsy_fails(self):
        self.assertFalse(
            _ga4_periodic_enabled(
                {
                    "sync_enabled": True,
                    "property_id": "123",
                    "read_project_id": "p",
                    "read_client_email": "x@y.iam",
                    "read_private_key_configured": False,  # missing
                }
            )
        )

    def test_matomo_all_truthy_passes(self):
        self.assertTrue(
            _matomo_periodic_enabled(
                {
                    "enabled": True,
                    "sync_enabled": True,
                    "url": "https://m",
                    "site_id_xenforo": "1",
                    "token_auth_configured": True,
                }
            )
        )

    def test_matomo_disabled_fails(self):
        self.assertFalse(
            _matomo_periodic_enabled(
                {
                    "enabled": False,
                    "sync_enabled": True,
                    "url": "https://m",
                    "site_id_xenforo": "1",
                    "token_auth_configured": True,
                }
            )
        )

    def test_gsc_all_truthy_passes(self):
        self.assertTrue(
            _gsc_periodic_enabled(
                {
                    "sync_enabled": True,
                    "property_url": "https://x",
                    "client_email": "x@y.iam",
                    "private_key_configured": True,
                }
            )
        )


class FormatBreakdownRowsTests(SimpleTestCase):
    """Verify the device/channel/country row formatter."""

    def test_label_or_unknown_used(self):
        rows = _format_breakdown_rows(
            [
                {
                    "device_category": None,
                    "impressions": 10,
                    "clicks": 1,
                    "engaged_sessions": 5,
                }
            ],
            "device_category",
        )
        self.assertEqual(rows[0]["label"], "Unknown")

    def test_zero_impressions_safe_ctr(self):
        rows = _format_breakdown_rows(
            [
                {
                    "device_category": "mobile",
                    "impressions": 0,
                    "clicks": 0,
                    "engaged_sessions": 0,
                }
            ],
            "device_category",
        )
        self.assertEqual(rows[0]["ctr"], 0.0)

    def test_int_coercion_handles_none(self):
        rows = _format_breakdown_rows(
            [
                {
                    "device_category": "mobile",
                    "impressions": None,
                    "clicks": None,
                    "engaged_sessions": None,
                }
            ],
            "device_category",
        )
        self.assertEqual(rows[0]["impressions"], 0)
        self.assertEqual(rows[0]["clicks"], 0)


class FormatTopSuggestionRowTests(SimpleTestCase):
    """Verify the top-suggestion row formatter."""

    def test_full_row_shape(self):
        result = _format_top_suggestion_row(
            {
                "suggestion_id": "abc-123",
                "suggestion__destination_title": "Page",
                "suggestion__anchor_phrase": "phrase",
                "suggestion__status": "applied",
                "telemetry_source": "ga4",
                "impressions": 100,
                "clicks": 10,
                "destination_views": 50,
                "engaged_sessions": 20,
                "conversions": 2,
                "quick_exit_sessions": 5,
                "dwell_60s_sessions": 15,
            }
        )
        self.assertEqual(result["suggestion_id"], "abc-123")
        self.assertEqual(result["destination_title"], "Page")
        self.assertEqual(result["ctr"], 0.1)  # 10/100
        self.assertEqual(result["engagement_rate"], 0.4)  # 20/50

    def test_missing_destination_title_fallback(self):
        result = _format_top_suggestion_row(
            {
                "suggestion_id": "abc",
                "suggestion__destination_title": None,
                "suggestion__anchor_phrase": None,
                "suggestion__status": None,
                "telemetry_source": "matomo",
                "impressions": 0,
                "clicks": 0,
                "destination_views": 0,
                "engaged_sessions": 0,
                "conversions": 0,
                "quick_exit_sessions": 0,
                "dwell_60s_sessions": 0,
            }
        )
        self.assertEqual(result["destination_title"], "Unknown destination")
        self.assertEqual(result["status"], "unknown")


class ResolveMatomoTestCredentialsTests(SimpleTestCase):
    """Verify Matomo test-credential resolution."""

    @mock.patch("apps.analytics.views._matomo_token", return_value="")
    @mock.patch("apps.analytics.views._read_setting", return_value="")
    def test_body_wins(self, _read, _token):
        creds = _resolve_matomo_test_credentials(
            {
                "url": "https://x.com/",
                "site_id_xenforo": "1",
                "token_auth": "tok",
            }
        )
        self.assertEqual(creds["base_url"], "https://x.com")
        self.assertEqual(creds["site_id"], "1")
        self.assertEqual(creds["token_auth"], "tok")


class ValidateOAuthCallbackInputsTests(SimpleTestCase):
    """Verify the callback-input guard's redirect URLs."""

    def _make_request(self, *, get_params: dict, session: dict | None = None):
        req = mock.Mock()
        req.GET = get_params
        req.session = session or {}
        return req

    def test_error_param_redirects(self):
        req = self._make_request(get_params={"error": "denied"})
        url = _validate_oauth_callback_inputs(req, "/settings")
        self.assertEqual(url, "/settings?oauth_error=denied")

    def test_missing_state_redirects(self):
        req = self._make_request(get_params={"code": "x"})
        url = _validate_oauth_callback_inputs(req, "/settings")
        self.assertEqual(url, "/settings?oauth_error=missing_params")

    def test_state_mismatch_redirects(self):
        req = self._make_request(
            get_params={"state": "bad", "code": "x"},
            session={"google_oauth_state": "good"},
        )
        url = _validate_oauth_callback_inputs(req, "/settings")
        self.assertEqual(url, "/settings?oauth_error=invalid_state")

    def test_valid_inputs_pass(self):
        req = self._make_request(
            get_params={"state": "good", "code": "x"},
            session={"google_oauth_state": "good"},
        )
        self.assertIsNone(_validate_oauth_callback_inputs(req, "/settings"))
