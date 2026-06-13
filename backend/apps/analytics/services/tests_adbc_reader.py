"""Tests for the ADBC Arrow-native Postgres reader.

The URI builder is a pure function over the live connection's settings,
so it tests in ``SimpleTestCase`` with no database. The actual ADBC
round-trip is proven by the telemetry-rollup and traffic-spike
integration tests (which run on committed data via TransactionTestCase).
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.analytics.services import adbc_reader


class PostgresUriTests(SimpleTestCase):
    def _uri_for(self, cfg: dict) -> str:
        # postgres_uri() does `from django.db import connection` at call
        # time, so patch settings_dict on the real connection object.
        with mock.patch("django.db.connection.settings_dict", cfg):
            return adbc_reader.postgres_uri()

    def test_builds_full_uri_with_credentials(self) -> None:
        uri = self._uri_for(
            {
                "USER": "xf_linker_user",
                "PASSWORD": "secret",
                "HOST": "postgres",
                "PORT": "5432",
                "NAME": "xf_linker",
            }
        )
        self.assertEqual(
            uri, "postgresql://xf_linker_user:secret@postgres:5432/xf_linker"
        )

    def test_uses_test_database_name_from_connection(self) -> None:
        # During tests Django rewrites NAME to the test DB; the builder must
        # reflect that so ADBC talks to the same DB the ORM is using.
        uri = self._uri_for(
            {
                "USER": "u",
                "PASSWORD": "p",
                "HOST": "postgres",
                "PORT": "5432",
                "NAME": "test_xf_linker",
            }
        )
        self.assertTrue(uri.endswith("/test_xf_linker"))

    def test_url_encodes_special_characters_in_password(self) -> None:
        uri = self._uri_for(
            {
                "USER": "u",
                "PASSWORD": "p@ss/w:rd",
                "HOST": "h",
                "PORT": "5432",
                "NAME": "db",
            }
        )
        self.assertIn("p%40ss%2Fw%3Ard", uri)
        self.assertNotIn("p@ss/w:rd", uri)

    def test_omits_auth_when_no_user(self) -> None:
        uri = self._uri_for(
            {"USER": "", "PASSWORD": "", "HOST": "h", "PORT": "5432", "NAME": "db"}
        )
        self.assertEqual(uri, "postgresql://h:5432/db")
