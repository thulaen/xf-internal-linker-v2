"""Checks that shared cache volumes are protected from cleanup."""

from __future__ import annotations

import json

from django.test import SimpleTestCase

from apps.audit.tests_tool_compose_integrity import PROTECTED_DATA_STORES_PATH


class ProtectedVolumeRegistryTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with PROTECTED_DATA_STORES_PATH.open("r", encoding="utf-8") as fh:
            cls.protected_data = json.load(fh)

    def test_hf_cache_volume_is_protected(self):
        self.assertIn(
            "hf_cache",
            self.protected_data["docker_volumes"],
            msg="`hf_cache` must be listed as a protected Docker volume.",
        )

    def test_hf_cache_is_not_marked_as_disposable_tool_cache(self):
        policy = self.protected_data["tool_cache_policy"]

        self.assertNotIn(
            "hf_cache",
            policy["deduped_cache_volumes"],
            msg="`hf_cache` stores model files for runtime workers, not disposable tool downloads.",
        )
