"""Convention-named SimpleTestCase coverage for apps/core/helper_router.py.

This file provides literal pinning to kill mutants and coverage for small pure 
functions in helper_router.py. DB/Network connections are completely avoided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core import helper_router


class HelperRouterConstantLiteralTests(SimpleTestCase):
    def test_heartbeat_fresh_seconds_is_120(self) -> None:
        self.assertEqual(helper_router.HEARTBEAT_FRESH_SECONDS, 120)

    def test_pct_to_fraction_is_0_01(self) -> None:
        self.assertEqual(helper_router._PCT_TO_FRACTION, 0.01)

    def test_demand_keys_exact(self) -> None:
        self.assertEqual(
            helper_router._DEMAND_KEYS, frozenset({"demand_cpu", "demand_ram_gb"})
        )


class InAllowedListTests(SimpleTestCase):
    def test_in_allowed_list_empty_allows_anything(self) -> None:
        self.assertTrue(helper_router._in_allowed_list(None, "anything"))
        self.assertTrue(helper_router._in_allowed_list([], "anything"))

    def test_in_allowed_list_match(self) -> None:
        self.assertTrue(helper_router._in_allowed_list(["a", "b"], "a"))

    def test_in_allowed_list_no_match(self) -> None:
        self.assertFalse(helper_router._in_allowed_list(["a", "b"], "c"))


class CheckFloorTests(SimpleTestCase):
    def test_check_floor_valid(self) -> None:
        have = {"key": 10}
        self.assertTrue(helper_router._check_floor(have, "key", 5))

    def test_check_floor_invalid(self) -> None:
        have = {"key": 10}
        self.assertFalse(helper_router._check_floor(have, "key", 15))

    def test_check_floor_fallback_to_equality(self) -> None:
        have = {"key": "value"}
        self.assertTrue(helper_router._check_floor(have, "key", "value"))
        self.assertFalse(helper_router._check_floor(have, "key", "other"))
