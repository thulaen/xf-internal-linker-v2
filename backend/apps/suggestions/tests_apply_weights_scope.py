"""Pin the post-2026-05-09 ``apply_weights`` scope behaviour.

Before 2026-05-09, ``apply_weights`` iterated every key in
``PRESET_DEFAULTS`` (~50 keys) and wrote each one — falling back to a
default when the caller didn't supply a value. That made every preset
application destructive: applying a small 4-key preset would silently
overwrite all ~46 unrelated keys, wiping any manual tweak or autotuner
output on those keys.

The fix: ``apply_weights`` now writes only the keys explicitly listed
in the supplied ``weights`` dict. These tests pin that invariant.
"""

from __future__ import annotations

from django.test import TestCase

from apps.core.models import AppSetting
from apps.suggestions.weight_preset_service import apply_weights


class ApplyWeightsScopeTests(TestCase):
    def test_writes_only_keys_present_in_weights_dict(self) -> None:
        """Pre-seed two AppSetting rows; apply a preset that lists ONE
        of them. The unlisted key must be unchanged."""
        AppSetting.objects.update_or_create(
            key="w_semantic",
            defaults={"value": "0.40", "value_type": "float", "category": "ml"},
        )
        AppSetting.objects.update_or_create(
            key="w_keyword",
            defaults={"value": "0.30", "value_type": "float", "category": "ml"},
        )

        # Preset only lists w_semantic.
        apply_weights({"w_semantic": "0.55"})

        self.assertEqual(
            AppSetting.objects.get(key="w_semantic").value, "0.55"
        )
        # The unlisted key is untouched — manual tweak survives.
        self.assertEqual(
            AppSetting.objects.get(key="w_keyword").value, "0.30"
        )

    def test_empty_weights_dict_is_a_noop(self) -> None:
        AppSetting.objects.update_or_create(
            key="w_semantic",
            defaults={"value": "0.40", "value_type": "float", "category": "ml"},
        )
        before = AppSetting.objects.count()
        apply_weights({})
        # The pre-seeded value is untouched.
        self.assertEqual(
            AppSetting.objects.get(key="w_semantic").value, "0.40"
        )
        # No row count changes — empty input is truly a no-op.
        self.assertEqual(AppSetting.objects.count(), before)

    def test_unknown_key_uses_defensive_meta_fallback(self) -> None:
        """A key not in ``_KEY_META`` writes successfully with the
        ``str``+``ml`` fallback shape, matching pre-fix behaviour."""
        apply_weights({"never.heard.of.this": "hello"})
        row = AppSetting.objects.get(key="never.heard.of.this")
        self.assertEqual(row.value, "hello")
        self.assertEqual(row.value_type, "str")
        self.assertEqual(row.category, "ml")

    def test_value_is_stringified(self) -> None:
        """Numeric inputs are coerced to string for AppSetting storage."""
        apply_weights({"w_semantic": 0.42})  # type: ignore[dict-item]
        self.assertEqual(
            AppSetting.objects.get(key="w_semantic").value, "0.42"
        )

    def test_overwrites_existing_value_for_listed_key(self) -> None:
        """The fix scopes WHICH keys get written, not WHETHER they get
        written — listed keys still overwrite their existing AppSetting
        row. This is the intentional behaviour for preset application."""
        AppSetting.objects.update_or_create(
            key="w_semantic",
            defaults={"value": "0.40", "value_type": "float", "category": "ml"},
        )
        apply_weights({"w_semantic": "0.99"})
        self.assertEqual(
            AppSetting.objects.get(key="w_semantic").value, "0.99"
        )
