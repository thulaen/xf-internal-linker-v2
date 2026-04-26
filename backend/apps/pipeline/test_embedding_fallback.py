"""Unit tests for graceful embedding-provider fallback (plan Part 8b, FR-234).

Covers:
  1. Auth error triggers fallback and switches AppSetting.
  2. Rate-limit error triggers fallback through the generic ProviderError path.
  3. No-loop guard: when the fallback provider equals the failing one, the
     helper returns None and the caller re-raises.
  4. SyncJob checkpoint is persisted before provider cache is cleared.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.core.models import AppSetting
from apps.pipeline.services import embeddings as embeddings_module
from apps.pipeline.services.embedding_providers.errors import (
    AuthenticationError,
    BudgetExceededError,
    RateLimitError,
)
from apps.sync.models import SyncJob


def _get_setting(key: str) -> str:
    row = AppSetting.objects.filter(key=key).first()
    return str(row.value).strip().lower() if row else ""


class FallbackHelperTests(TestCase):
    """``_attempt_graceful_fallback`` unit tests that exercise the helper alone."""

    def setUp(self) -> None:
        AppSetting.objects.update_or_create(
            key="embedding.provider", defaults={"value": "openai"}
        )
        AppSetting.objects.update_or_create(
            key="embedding.fallback_provider", defaults={"value": "local"}
        )

    def test_auth_error_triggers_provider_swap(self) -> None:
        fake_new_provider = mock.MagicMock(name="local-provider")
        with (
            mock.patch(
                "apps.pipeline.services.embedding_providers.clear_cache"
            ) as clear,
            mock.patch(
                "apps.pipeline.services.embedding_providers.get_provider",
                return_value=fake_new_provider,
            ) as getp,
        ):
            result = embeddings_module._attempt_graceful_fallback(
                failing_provider_name="openai",
                reason="401 Unauthorized",
                reason_code="auth",
            )
        self.assertIs(result, fake_new_provider)
        self.assertEqual(_get_setting("embedding.provider"), "local")
        clear.assert_called_once()
        getp.assert_called_once()

    def test_rate_limit_code_path_also_swaps(self) -> None:
        fake_new_provider = mock.MagicMock(name="local-provider")
        with (
            mock.patch("apps.pipeline.services.embedding_providers.clear_cache"),
            mock.patch(
                "apps.pipeline.services.embedding_providers.get_provider",
                return_value=fake_new_provider,
            ),
        ):
            result = embeddings_module._attempt_graceful_fallback(
                failing_provider_name="openai",
                reason="429 Too Many Requests",
                reason_code="rate_limit",
            )
        self.assertIs(result, fake_new_provider)
        self.assertEqual(_get_setting("embedding.provider"), "local")

    def test_no_loop_guard_returns_none_when_fallback_equals_failing(self) -> None:
        AppSetting.objects.update_or_create(
            key="embedding.fallback_provider", defaults={"value": "openai"}
        )
        result = embeddings_module._attempt_graceful_fallback(
            failing_provider_name="openai",
            reason="401",
            reason_code="auth",
        )
        self.assertIsNone(result)
        # Provider must stay put — no silent swap to a bad target.
        self.assertEqual(_get_setting("embedding.provider"), "openai")

    def test_checkpoint_persisted_before_cache_cleared(self) -> None:
        job = SyncJob.objects.create(
            source="api",
            mode="full",
            status="running",
            is_resumable=False,
        )
        clear_order: list[str] = []

        def _record_clear() -> None:
            clear_order.append("clear")

        original_save = embeddings_module._save_fallback_checkpoint

        def _recording_save(**kwargs):
            clear_order.append("checkpoint")
            return original_save(**kwargs)

        with (
            mock.patch(
                "apps.pipeline.services.embedding_providers.clear_cache",
                side_effect=_record_clear,
            ),
            mock.patch(
                "apps.pipeline.services.embedding_providers.get_provider",
                return_value=mock.MagicMock(),
            ),
            mock.patch.object(
                embeddings_module,
                "_save_fallback_checkpoint",
                side_effect=_recording_save,
            ),
        ):
            embeddings_module._attempt_graceful_fallback(
                failing_provider_name="openai",
                reason="401",
                reason_code="auth",
                job_id=str(job.job_id),
            )

        self.assertEqual(clear_order, ["checkpoint", "clear"])

        job.refresh_from_db()
        self.assertTrue(job.is_resumable)
        self.assertEqual(job.checkpoint_stage, "embed_fallback")
        self.assertIn("openai", job.message)
        self.assertIn("local", job.message)


class EncodeBatchFallbackTests(TestCase):
    """End-to-end: ``_encode_batch_via_provider`` swaps provider on failure."""

    def setUp(self) -> None:
        AppSetting.objects.update_or_create(
            key="embedding.provider", defaults={"value": "openai"}
        )
        AppSetting.objects.update_or_create(
            key="embedding.fallback_provider", defaults={"value": "local"}
        )

    def _build_provider(
        self, *, name: str, raise_exc: Exception | None, result_vectors
    ):
        provider = mock.MagicMock(name=f"{name}-provider")
        provider.name = name
        provider.signature = f"{name}:model:1024"
        if raise_exc is not None:
            provider.embed.side_effect = raise_exc
        else:
            provider.embed.return_value = mock.MagicMock(
                vectors=result_vectors, tokens_input=0, cost_usd=0.0
            )
        return provider

    def test_budget_error_switches_to_fallback_and_retries_batch(self) -> None:
        import numpy as np

        failing = self._build_provider(
            name="openai",
            raise_exc=BudgetExceededError("monthly cap hit", reason="budget"),
            result_vectors=None,
        )
        good = self._build_provider(
            name="local",
            raise_exc=None,
            result_vectors=np.zeros((2, 1024), dtype=np.float32),
        )

        with (
            mock.patch(
                "apps.pipeline.services.embedding_providers.get_provider",
                side_effect=[failing, good],
            ),
            mock.patch("apps.pipeline.services.embedding_providers.clear_cache"),
            mock.patch.object(embeddings_module.time, "sleep") as fake_sleep,
        ):
            vectors = embeddings_module._encode_batch_via_provider(
                batch_texts=["a", "b"],
                model=None,
                batch_size=2,
                job_id=None,
            )
        self.assertEqual(vectors.shape, (2, 1024))
        failing.embed.assert_called_once()
        good.embed.assert_called_once()
        fake_sleep.assert_called_once_with(
            embeddings_module._FALLBACK_RETRY_COOLDOWN_SECONDS
        )

    def test_auth_error_via_generic_provider_error_swaps(self) -> None:
        import numpy as np

        failing = self._build_provider(
            name="openai",
            raise_exc=AuthenticationError("401 bad key", reason="auth"),
            result_vectors=None,
        )
        good = self._build_provider(
            name="local",
            raise_exc=None,
            result_vectors=np.zeros((1, 1024), dtype=np.float32),
        )

        with (
            mock.patch(
                "apps.pipeline.services.embedding_providers.get_provider",
                side_effect=[failing, good],
            ),
            mock.patch("apps.pipeline.services.embedding_providers.clear_cache"),
            mock.patch.object(embeddings_module.time, "sleep") as fake_sleep,
        ):
            vectors = embeddings_module._encode_batch_via_provider(
                batch_texts=["x"],
                model=None,
                batch_size=1,
                job_id=None,
            )
        self.assertEqual(vectors.shape, (1, 1024))
        fake_sleep.assert_called_once()

    def test_unrecoverable_reason_code_reraises_without_swap(self) -> None:
        from apps.pipeline.services.embedding_providers.errors import ProviderError

        failing = self._build_provider(
            name="openai",
            raise_exc=ProviderError("unknown error", reason="invalid_input"),
            result_vectors=None,
        )
        with mock.patch(
            "apps.pipeline.services.embedding_providers.get_provider",
            return_value=failing,
        ):
            with self.assertRaises(ProviderError):
                embeddings_module._encode_batch_via_provider(
                    batch_texts=["x"],
                    model=None,
                    batch_size=1,
                    job_id=None,
                )
        # Provider must still be openai — no swap for unrecoverable errors.
        self.assertEqual(_get_setting("embedding.provider"), "openai")

    def test_rate_limit_cooldown_is_applied(self) -> None:
        import numpy as np

        failing = self._build_provider(
            name="openai",
            raise_exc=RateLimitError("429", reason="rate_limit"),
            result_vectors=None,
        )
        good = self._build_provider(
            name="local",
            raise_exc=None,
            result_vectors=np.zeros((1, 1024), dtype=np.float32),
        )

        with (
            mock.patch(
                "apps.pipeline.services.embedding_providers.get_provider",
                side_effect=[failing, good],
            ),
            mock.patch("apps.pipeline.services.embedding_providers.clear_cache"),
            mock.patch.object(embeddings_module.time, "sleep") as fake_sleep,
        ):
            embeddings_module._encode_batch_via_provider(
                batch_texts=["x"],
                model=None,
                batch_size=1,
                job_id=None,
            )

        fake_sleep.assert_called_once_with(
            embeddings_module._FALLBACK_RETRY_COOLDOWN_SECONDS
        )
