"""SimpleTestCase coverage for the embedding provider factory.

The factory lives in ``embedding_providers/__init__.py``. The scoped mutation
gate deliberately SKIPS ``__init__.py`` source files (see
``.githooks/check-scoped-mutation.py`` — the skip regex includes
``/__init__\\.py$``), so the convention name ``tests___init__.py`` would never
be discovered for that source. This file is therefore a normal pytest-discovered
test (its stem matches no mutated source, so the gate ignores it too) and pins
the two recent behaviour changes:

* ``_read_provider_name`` now defaults to ``"openai"`` (was ``"local"``) when no
  ``AppSetting("embedding.provider")`` row exists.
* ``_instantiate`` raises ``ProviderError`` (reason ``"invalid_provider"``) on an
  unknown provider name instead of falling back.

Hang-safe: ``AppSetting`` and the concrete provider classes are mocked, so no
real model, network, or API client is constructed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.pipeline.services.embedding_providers import (
    _instantiate,
    _read_provider_name,
    clear_cache,
    get_provider,
)
from apps.pipeline.services.embedding_providers.errors import ProviderError


class ReadProviderNameTests(SimpleTestCase):
    """The default provider name is openai when no setting/row is present."""

    def setUp(self) -> None:
        clear_cache()
        self.addCleanup(clear_cache)

    def test_default_is_openai_when_no_setting_row(self) -> None:
        fake_setting = MagicMock()
        fake_setting.objects.filter.return_value.first.return_value = None
        with patch.dict(
            "sys.modules", {"apps.core.models": MagicMock(AppSetting=fake_setting)}
        ):
            # Exact-equality kills a "openai" -> "XXopenaiXX" string mutant.
            self.assertEqual(_read_provider_name(), "openai")

    def test_setting_value_is_lowercased_and_stripped(self) -> None:
        fake_setting = MagicMock()
        row = MagicMock()
        row.value = "  GEMINI  "
        fake_setting.objects.filter.return_value.first.return_value = row
        with patch.dict(
            "sys.modules", {"apps.core.models": MagicMock(AppSetting=fake_setting)}
        ):
            self.assertEqual(_read_provider_name(), "gemini")


class InstantiateUnknownProviderTests(SimpleTestCase):
    """_instantiate raises ProviderError on an unknown provider name."""

    def test_unknown_provider_raises_provider_error(self) -> None:
        with self.assertRaises(ProviderError) as ctx:
            _instantiate("not_a_real_provider")
        # Exact reason match kills a reason="invalid_provider" string mutant.
        self.assertEqual(ctx.exception.reason, "invalid_provider")

    def test_unknown_provider_message_names_the_bad_value(self) -> None:
        with self.assertRaises(ProviderError) as ctx:
            _instantiate("not_a_real_provider")
        self.assertEqual(
            str(ctx.exception),
            "Unknown embedding.provider='not_a_real_provider'; "
            "choose one of: openai, gemini",
        )


class GetProviderFactoryTests(SimpleTestCase):
    """get_provider resolves and caches the named provider instance."""

    def setUp(self) -> None:
        clear_cache()
        self.addCleanup(clear_cache)

    def test_openai_name_builds_openai_provider(self) -> None:
        sentinel = object()
        fake_module = MagicMock()
        fake_module.OpenAIProvider.return_value = sentinel
        with patch(
            "apps.pipeline.services.embedding_providers._read_provider_name",
            return_value="openai",
        ), patch.dict(
            "sys.modules",
            {"apps.pipeline.services.embedding_providers.openai_provider": fake_module},
        ):
            self.assertIs(get_provider(), sentinel)
            fake_module.OpenAIProvider.assert_called_once_with()

    def test_unknown_name_propagates_provider_error(self) -> None:
        with patch(
            "apps.pipeline.services.embedding_providers._read_provider_name",
            return_value="bogus",
        ):
            with self.assertRaises(ProviderError):
                get_provider()
