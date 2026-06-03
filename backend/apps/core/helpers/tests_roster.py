"""Convention-named SimpleTestCase coverage for apps/core/helpers/roster.py.

This file provides literal pinning to kill mutants and coverage for small pure 
functions in roster.py. DB/Network connections are completely avoided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.helpers import roster


class RosterConstantLiteralTests(SimpleTestCase):
    def test_cache_key_exact(self) -> None:
        self.assertEqual(roster.CACHE_KEY, "helpers.roster")

    def test_cache_ttl_seconds_is_60(self) -> None:
        self.assertEqual(roster.CACHE_TTL_SECONDS, 60)


class RosterTests(SimpleTestCase):
    def test_roster_cache_hit_returns_cached(self) -> None:
        cached_snapshot = MagicMock()
        with patch.object(roster.cache, "get", return_value=cached_snapshot) as mock_get:
            result = roster.roster(force_refresh=False)
            self.assertEqual(result, cached_snapshot)
            mock_get.assert_called_once_with(roster.CACHE_KEY)

    def test_roster_force_refresh_bypasses_cache(self) -> None:
        snapshot = MagicMock()
        with patch.object(roster, "_build_roster", return_value=snapshot) as mock_build, \
             patch.object(roster.cache, "set") as mock_set:
            result = roster.roster(force_refresh=True)
            self.assertEqual(result, snapshot)
            mock_build.assert_called_once()
            mock_set.assert_called_once_with(roster.CACHE_KEY, snapshot, 60)
