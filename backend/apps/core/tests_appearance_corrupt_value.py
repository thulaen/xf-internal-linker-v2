"""Regression test for AutoIssue #20375.

A corrupt JSON value stored in the ``appearance.config`` AppSetting row used to
crash the appearance settings endpoints with an uncaught ``JSONDecodeError``
(HTTP 500). Both read paths now route the stored blob through the guarded
``AppSetting.get_json`` helper, which returns the supplied default on a parse
failure instead of raising.

Covers the changed lines in ``apps/core/views_settings.py``:
``AppearanceSettingsView._get_config`` and the module-level
``_save_appearance_key``. Kept as a ``SimpleTestCase`` by mocking the ORM read
so no database row is required.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.core.views import DEFAULT_APPEARANCE
from apps.core.views_settings import AppearanceSettingsView, _save_appearance_key


class _FakeSetting:
    """Stand-in for an AppSetting row whose stored value is corrupt JSON."""

    def __init__(self, value: str) -> None:
        self.value = value


class CorruptAppearanceConfigTests(SimpleTestCase):
    CORRUPT = "{not valid json"

    def test_get_config_degrades_to_defaults_on_corrupt_value(self) -> None:
        """When the stored blob is unparseable, _get_config returns the pure defaults."""
        with mock.patch(
            "apps.core.models.AppSetting.get_str", return_value=self.CORRUPT
        ):
            config = AppearanceSettingsView()._get_config()

        self.assertEqual(config, dict(DEFAULT_APPEARANCE))

    def test_get_config_does_not_raise_on_corrupt_value(self) -> None:
        """The corrupt-value path must not raise JSONDecodeError / ValueError."""
        with mock.patch(
            "apps.core.models.AppSetting.get_str", return_value=self.CORRUPT
        ):
            try:
                AppearanceSettingsView()._get_config()
            except ValueError as exc:  # JSONDecodeError is a ValueError subclass
                self.fail(f"_get_config raised on corrupt stored value: {exc!r}")

    def test_get_config_degrades_to_defaults_on_non_dict_value(self) -> None:
        """A valid-JSON-but-non-dict blob (e.g. a list) also degrades to defaults."""
        with mock.patch(
            "apps.core.models.AppSetting.get_str", return_value="[1, 2, 3]"
        ):
            config = AppearanceSettingsView()._get_config()

        self.assertEqual(config, dict(DEFAULT_APPEARANCE))

    def test_get_config_keeps_valid_stored_override(self) -> None:
        """A valid dict blob still overrides the matching default key exactly."""
        with mock.patch(
            "apps.core.models.AppSetting.get_str",
            return_value='{"siteName": "Custom"}',
        ):
            config = AppearanceSettingsView()._get_config()

        self.assertEqual(config["siteName"], "Custom")

    def test_save_appearance_key_recovers_from_corrupt_existing_blob(self) -> None:
        """_save_appearance_key must start from {} (not crash) when the existing blob is corrupt."""
        captured = {}

        def _fake_update_or_create(*, key, defaults):
            captured["defaults"] = defaults
            return (_FakeSetting(defaults["value"]), True)

        with mock.patch(
            "apps.core.models.AppSetting.get_str", return_value=self.CORRUPT
        ), mock.patch(
            "apps.core.models.AppSetting.objects.update_or_create",
            side_effect=_fake_update_or_create,
        ):
            _save_appearance_key("primaryColor", "#000000")

        import json

        stored = json.loads(captured["defaults"]["value"])
        self.assertEqual(stored, {"primaryColor": "#000000"})
