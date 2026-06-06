"""Tests for the pure-function helpers extracted from pipeline/services/embeddings.py.

These helpers replaced ~600 lines of inlined branching across the 8 long
``_*`` and ``generate_*_embeddings`` entrypoints. Each is independently
testable in ``SimpleTestCase`` (no DB) so a future tweak to a coefficient
or threshold shows up here before it ships.
"""

from __future__ import annotations

from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services import embeddings as embeddings_module
from apps.pipeline.services.embeddings import (
    L2NormalizationAuditError,
    _audit_l2_normalization,
    _build_content_item_text_inputs,
    _build_sentence_text_inputs,
    _emit_fallback_alert,
    _encode_batch_via_provider,
    _extract_existing_quality_gate_inputs,
    _load_legacy_model_or_none,
    _load_model,
    _PROVIDER_FALLBACK_REASON_CODES,
    _quality_gate_should_skip,
    _thermal_guard_before_gpu_batch,
    generate_content_item_embeddings,
    generate_sentence_embeddings,
    get_model_status,
)


class BuildContentItemTextInputsTests(SimpleTestCase):
    """``_build_content_item_text_inputs`` builds the (pks, texts, hashes) triple."""

    def test_clean_text_preferred_over_distilled(self):
        items = [(1, "Title", "Long clean body", "Distilled summary")]
        pks, texts, hashes = _build_content_item_text_inputs(items)
        self.assertEqual(pks, [1])
        self.assertEqual(texts[0], "Title\n\nLong clean body")
        self.assertEqual(len(hashes), 1)

    def test_distilled_fallback_when_clean_empty(self):
        items = [(1, "Title", "", "Distilled summary")]
        _, texts, _ = _build_content_item_text_inputs(items)
        self.assertEqual(texts[0], "Title\n\nDistilled summary")

    def test_title_only_when_no_body(self):
        items = [(1, "Title", "", "")]
        _, texts, _ = _build_content_item_text_inputs(items)
        self.assertEqual(texts[0], "Title")

    def test_skips_completely_empty_rows(self):
        items = [(1, "", "", ""), (2, "Real Title", "Real body", "")]
        pks, texts, hashes = _build_content_item_text_inputs(items)
        self.assertEqual(pks, [2])
        self.assertEqual(len(texts), 1)
        self.assertEqual(len(hashes), 1)

    def test_lengths_align(self):
        # The (pks, texts, hashes) lists MUST stay length-aligned for
        # _flush_embeddings_slice's zip(strict=True) to not raise.
        items = [(i, f"T{i}", f"B{i}", "") for i in range(5)]
        pks, texts, hashes = _build_content_item_text_inputs(items)
        self.assertEqual(len(pks), len(texts))
        self.assertEqual(len(texts), len(hashes))


class BuildSentenceTextInputsTests(SimpleTestCase):
    """``_build_sentence_text_inputs`` skips empty/whitespace sentences."""

    def test_strips_whitespace(self):
        sentences = [(1, "  hello  "), (2, "world")]
        pks, texts = _build_sentence_text_inputs(sentences)
        self.assertEqual(texts, ["hello", "world"])
        self.assertEqual(pks, [1, 2])

    def test_skips_empty_text(self):
        sentences = [(1, ""), (2, "real")]
        pks, texts = _build_sentence_text_inputs(sentences)
        self.assertEqual(pks, [2])
        self.assertEqual(texts, ["real"])

    def test_skips_whitespace_only(self):
        sentences = [(1, "   "), (2, "real")]
        pks, _ = _build_sentence_text_inputs(sentences)
        self.assertEqual(pks, [2])

    def test_skips_none_text(self):
        sentences = [(1, None), (2, "real")]
        pks, _ = _build_sentence_text_inputs(sentences)
        self.assertEqual(pks, [2])


class ProviderFallbackReasonCodesTests(SimpleTestCase):
    """The fallback whitelist that ``_encode_via_provider_with_fallback`` honours."""

    def test_contains_all_recoverable_codes(self):
        # Per FR-234 these are the four codes that are safe to swap on.
        self.assertIn("auth", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertIn("rate_limit", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertIn("budget", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertIn("transient", _PROVIDER_FALLBACK_REASON_CODES)

    def test_does_not_contain_irrecoverable_codes(self):
        # provider_error / unknown / etc must propagate so the operator sees them.
        self.assertNotIn("provider_error", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertNotIn("unknown", _PROVIDER_FALLBACK_REASON_CODES)


class QualityGateShouldSkipTests(SimpleTestCase):
    """``_quality_gate_should_skip`` checks model class + non-empty pks + signature."""

    def _model(self, name: str):
        m = mock.Mock()
        m.__name__ = name
        return m

    def test_non_content_item_skipped(self):
        self.assertTrue(
            _quality_gate_should_skip(
                model_class=self._model("Sentence"),
                pks_slice=[1, 2],
                embedding_signature="bge-m3-v1",
            )
        )

    def test_empty_pks_skipped(self):
        self.assertTrue(
            _quality_gate_should_skip(
                model_class=self._model("ContentItem"),
                pks_slice=[],
                embedding_signature="bge-m3-v1",
            )
        )

    def test_no_signature_skipped(self):
        self.assertTrue(
            _quality_gate_should_skip(
                model_class=self._model("ContentItem"),
                pks_slice=[1],
                embedding_signature=None,
            )
        )

    def test_all_satisfied_does_not_skip(self):
        self.assertFalse(
            _quality_gate_should_skip(
                model_class=self._model("ContentItem"),
                pks_slice=[1],
                embedding_signature="bge-m3-v1",
            )
        )


class ExtractExistingQualityGateInputsTests(SimpleTestCase):
    """``_extract_existing_quality_gate_inputs`` pulls (old_vec, old_sig, text) from a row."""

    def test_none_row_returns_defaults(self):
        old_vec, old_sig, text = _extract_existing_quality_gate_inputs(None, True)
        self.assertIsNone(old_vec)
        self.assertEqual(old_sig, "")
        self.assertIsNone(text)

    def test_row_without_embedding_returns_none_vec(self):
        row = {
            "embedding": None,
            "embedding_model_version": "bge-v1",
            "title": "T",
            "distilled_text": "D",
        }
        old_vec, old_sig, text = _extract_existing_quality_gate_inputs(row, True)
        self.assertIsNone(old_vec)
        self.assertEqual(old_sig, "bge-v1")
        self.assertEqual(text, "T\n\nD")

    def test_row_with_valid_embedding(self):
        row = {
            "embedding": [0.1, 0.2, 0.3],
            "embedding_model_version": "v1",
            "title": "Title",
            "distilled_text": "Body",
        }
        old_vec, old_sig, text = _extract_existing_quality_gate_inputs(row, True)
        self.assertIsNotNone(old_vec)
        self.assertEqual(old_vec.shape, (3,))
        self.assertEqual(old_sig, "v1")
        self.assertEqual(text, "Title\n\nBody")

    def test_no_signature_field(self):
        # When the model doesn't have embedding_model_version, sig should be "".
        row = {"embedding": None, "title": "T", "distilled_text": "D"}
        _, old_sig, _ = _extract_existing_quality_gate_inputs(row, False)
        self.assertEqual(old_sig, "")

    def test_corrupt_embedding_becomes_none(self):
        # asarray fails on a non-numeric value → fall back to None so the
        # gate accepts the new vector.
        row = {
            "embedding": ["not-a-number", "really"],
            "title": "T",
            "distilled_text": "D",
        }
        old_vec, _, _ = _extract_existing_quality_gate_inputs(row, False)
        self.assertIsNone(old_vec)


class AuditL2NormalizationTests(SimpleTestCase):
    """FR-237 — audit catches drift from the L2-unit invariant.

    Sources of truth: Wang et al. 2017 NAACL §2 (cosine on un-normalized
    vectors is biased by magnitude); IEEE 754-2019 §5.4 (single-precision
    rounding tolerance for unit-magnitude floats is below 1e-6).
    """

    def _unit_batch(self, n: int = 3, dim: int = 8) -> np.ndarray:
        rng = np.random.default_rng(seed=42)
        raw = rng.standard_normal((n, dim)).astype(np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        return (raw / norms).astype(np.float32)

    def test_passes_unit_normalized_batch(self):
        # Happy path: a fresh L2-unit batch passes silently.
        _audit_l2_normalization(self._unit_batch())

    def test_no_op_on_empty_array(self):
        # Edge case: zero-row arrays are valid (the flush path produces
        # them when the quality gate filters everything).
        _audit_l2_normalization(np.zeros((0, 1024), dtype=np.float32))

    def test_raises_on_zero_vector_row(self):
        # Adversarial: a row of all-zeros has norm 0; deviation = 1.0.
        batch = self._unit_batch()
        batch[1] = 0.0
        with self.assertRaises(L2NormalizationAuditError) as ctx:
            _audit_l2_normalization(batch)
        self.assertEqual(ctx.exception.worst_row, 1)
        self.assertAlmostEqual(ctx.exception.max_dev, 1.0, places=5)

    def test_raises_on_inflated_vector(self):
        # Adversarial: a row pre-multiplied by 1.5 fails the audit.
        batch = self._unit_batch()
        batch[2] = batch[2] * 1.5
        with self.assertRaises(L2NormalizationAuditError) as ctx:
            _audit_l2_normalization(batch)
        self.assertEqual(ctx.exception.worst_row, 2)
        self.assertAlmostEqual(ctx.exception.max_dev, 0.5, places=5)

    def test_carries_n_rows_in_error(self):
        # Diagnostic: the error message must show batch size so operators
        # can tell whether the failure is a one-off row or a corrupt batch.
        batch = self._unit_batch(n=5)
        batch[4] = 0.0
        with self.assertRaises(L2NormalizationAuditError) as ctx:
            _audit_l2_normalization(batch)
        self.assertEqual(ctx.exception.n_rows, 5)
        self.assertEqual(ctx.exception.worst_row, 4)

    def test_tolerance_override_accepts_loose_match(self):
        # A 1e-3-tolerance allows a row that's 0.999 instead of 1.0 — useful
        # for fp16 GPU pipelines where rounding is coarser than fp32.
        batch = self._unit_batch()
        batch[0] = batch[0] * 0.999
        # default tolerance (1e-6) would fail
        with self.assertRaises(L2NormalizationAuditError):
            _audit_l2_normalization(batch)
        # loosened tolerance accepts it
        _audit_l2_normalization(batch, tolerance=1e-2)

    def test_within_ieee754_single_precision_tolerance(self):
        # The IEEE 754-2019 §5.4 single-precision unit-magnitude epsilon is
        # ~6e-8. A row that drifts by 5e-7 (still very tight) must pass at
        # the default 1e-6 tolerance.
        batch = self._unit_batch()
        batch[0] = batch[0] * (1.0 + 5e-7)
        _audit_l2_normalization(batch)


class LoadModelCompatibilityHookTests(SimpleTestCase):
    """The provider migration left thin compatibility hooks the old call
    sites and tests still reach for. They must keep working so callers do
    not crash after the local-model code was removed.
    """

    def test_load_model_delegates_to_get_provider(self):
        # ``_load_model`` now returns whatever ``get_provider`` returns —
        # the local-model loader was deleted in the paid-provider migration.
        sentinel = mock.Mock(name="provider")
        with mock.patch(
            "apps.pipeline.services.embedding_providers.get_provider",
            return_value=sentinel,
        ) as get_provider:
            self.assertIs(_load_model("ignored-arg", extra="ignored-kw"), sentinel)
        get_provider.assert_called_once_with()

    def test_legacy_model_returned_only_when_it_has_encode(self):
        # A real legacy local model exposes ``.encode``; that is the signal
        # the generate_* paths use to take the local-encode branch.
        encodable = mock.Mock(name="legacy-model")
        encodable.encode = lambda texts: texts
        with mock.patch.object(
            embeddings_module, "_load_model", return_value=encodable
        ):
            self.assertIs(_load_legacy_model_or_none(), encodable)

    def test_legacy_model_is_none_when_provider_has_no_encode(self):
        # The paid provider has no ``.encode`` attribute, so the legacy hook
        # must report "no local model" and let the provider path run.
        provider = mock.Mock(spec=["embed", "name", "signature"])
        with mock.patch.object(
            embeddings_module, "_load_model", return_value=provider
        ):
            self.assertIsNone(_load_legacy_model_or_none())

    def test_legacy_model_is_none_when_loader_raises(self):
        # If the hook itself blows up, the caller must get None (and keep
        # going through the provider) rather than a propagated exception.
        with mock.patch.object(
            embeddings_module,
            "_load_model",
            side_effect=RuntimeError("no local model installed"),
        ):
            self.assertIsNone(_load_legacy_model_or_none())

    def test_thermal_guard_is_a_noop(self):
        # Provider-backed embeddings never run a local GPU batch, so the
        # thermal guard is a no-op that must accept any args and return None.
        self.assertIsNone(_thermal_guard_before_gpu_batch())
        self.assertIsNone(_thermal_guard_before_gpu_batch(1, 2, device="cuda"))


class EncodeBatchLocalModelFastPathTests(SimpleTestCase):
    """``_encode_batch_via_provider`` short-circuits to ``model.encode`` when a
    legacy local model is supplied, skipping the paid-provider path entirely.
    """

    def test_uses_model_encode_when_model_has_encode(self):
        captured = {}

        class _LocalModel:
            def encode(self, texts):
                captured["texts"] = list(texts)
                return [[0.1, 0.2], [0.3, 0.4]]

        # ``_try_get_active_provider`` must NOT be called on the fast path.
        with mock.patch.object(
            embeddings_module, "_try_get_active_provider"
        ) as provider_getter:
            out = _encode_batch_via_provider(
                batch_texts=["a", "b"],
                model=_LocalModel(),
                batch_size=2,
                job_id=None,
            )
        provider_getter.assert_not_called()
        self.assertEqual(captured["texts"], ["a", "b"])
        self.assertEqual(out.dtype, np.float32)
        self.assertEqual(out.shape, (2, 2))
        self.assertAlmostEqual(float(out[0, 0]), 0.1, places=6)


class GetModelStatusModelCacheTests(SimpleTestCase):
    """``get_model_status`` looks up a cached model handle keyed by
    ``<model_name>::<device>`` and forwards it to ``_describe_model_runtime``.
    """

    def setUp(self):
        # The module-level cache is shared state; isolate each test.
        self._saved_cache = dict(embeddings_module._model_cache)
        embeddings_module._model_cache.clear()
        self.addCleanup(self._restore_cache)

    def _restore_cache(self):
        embeddings_module._model_cache.clear()
        embeddings_module._model_cache.update(self._saved_cache)

    def test_cached_model_is_passed_to_describe_runtime(self):
        cached_handle = mock.Mock(name="cached-model")
        runtime = {
            "performance_mode": "high",
            "effective_runtime_mode": "api",
            "device": "api",
            "reason": "paid embedding provider",
        }
        embeddings_module._model_cache["bge-m3::api"] = cached_handle

        with (
            mock.patch.object(
                embeddings_module, "_get_model_name", return_value="bge-m3"
            ),
            mock.patch.object(
                embeddings_module,
                "get_effective_runtime_resolution",
                return_value=runtime,
            ),
            mock.patch.object(
                embeddings_module, "_get_configured_batch_size", return_value=32
            ),
            mock.patch.object(embeddings_module, "_get_batch_size", return_value=16),
            mock.patch.object(
                embeddings_module, "_describe_model_runtime"
            ) as describe,
        ):
            describe.return_value = {
                "configured_batch_size": 32,
                "embedding_dim": 1024,
                "active_signature": "sig",
                "storage_dimension_cap": 16000,
                "dimension_compatible": True,
            }
            status = get_model_status()

        # The cached handle for "bge-m3::api" must be forwarded, not None.
        self.assertIs(describe.call_args.kwargs["model"], cached_handle)
        self.assertEqual(status["device"], "api")
        self.assertEqual(status["embedding_dim"], 1024)

    def test_missing_cache_entry_forwards_none(self):
        runtime = {
            "performance_mode": "high",
            "effective_runtime_mode": "api",
            "device": "api",
            "reason": "paid embedding provider",
        }
        with (
            mock.patch.object(
                embeddings_module, "_get_model_name", return_value="bge-m3"
            ),
            mock.patch.object(
                embeddings_module,
                "get_effective_runtime_resolution",
                return_value=runtime,
            ),
            mock.patch.object(
                embeddings_module, "_get_configured_batch_size", return_value=32
            ),
            mock.patch.object(embeddings_module, "_get_batch_size", return_value=16),
            mock.patch.object(
                embeddings_module, "_describe_model_runtime"
            ) as describe,
        ):
            describe.return_value = {
                "configured_batch_size": 32,
                "embedding_dim": 1024,
                "active_signature": "sig",
                "storage_dimension_cap": 16000,
                "dimension_compatible": True,
            }
            get_model_status()

        # Nothing cached for this key → None is forwarded.
        self.assertIsNone(describe.call_args.kwargs["model"])


class EmitFallbackAlertContractTests(SimpleTestCase):
    """``_emit_fallback_alert`` raises an OperatorAlert with the FR-234
    fallback contract: event type, severity, dedupe key, route, and payload.
    """

    def test_emits_operator_alert_with_full_contract(self):
        with mock.patch(
            "apps.notifications.services.emit_operator_alert"
        ) as emit_alert:
            _emit_fallback_alert(
                failing="openai",
                fallback="local",
                reason_code="auth",
                reason_message="token expired",
            )

        kwargs = emit_alert.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "embedding.provider_fallback")
        self.assertEqual(kwargs["severity"], "warning")
        self.assertEqual(kwargs["title"], "Embedding provider fallback active")
        self.assertIn("openai", kwargs["message"])
        self.assertIn("local", kwargs["message"])
        self.assertEqual(
            kwargs["dedupe_key"], "embedding.provider_fallback:openai:local"
        )
        self.assertEqual(kwargs["related_route"], "/jobs")
        self.assertEqual(kwargs["payload"]["reason_code"], "auth")
        self.assertEqual(kwargs["payload"]["failing_provider"], "openai")
        self.assertEqual(kwargs["payload"]["fallback_provider"], "local")

    def test_swallows_alert_failure_without_raising(self):
        # The alert surface is best-effort: a failure must NOT bubble up and
        # block the embedding fallback itself.
        with mock.patch(
            "apps.notifications.services.emit_operator_alert",
            side_effect=RuntimeError("alert pipe down"),
        ):
            self.assertIsNone(
                _emit_fallback_alert(
                    failing="openai",
                    fallback="local",
                    reason_code="auth",
                    reason_message="boom",
                )
            )


class GenerateEmbeddingsModelResolutionTests(SimpleTestCase):
    """The ``generate_*_embeddings`` entrypoints resolve model_name + signature
    differently depending on whether a legacy local model is present, then
    return early when their queryset is empty. These tests pin that preamble.
    """

    def _legacy_model(self):
        m = mock.Mock(name="legacy-model")
        m.encode = lambda texts: texts
        return m

    def test_content_item_uses_legacy_model_signature_when_present(self):
        legacy = self._legacy_model()
        with (
            mock.patch.object(embeddings_module, "_try_get_active_provider"),
            mock.patch.object(
                embeddings_module, "_load_legacy_model_or_none", return_value=legacy
            ),
            mock.patch.object(
                embeddings_module, "_get_model_name", return_value="local-bge"
            ),
            mock.patch.object(
                embeddings_module,
                "get_current_embedding_signature",
                return_value="local-sig",
            ) as get_sig,
            mock.patch.object(embeddings_module, "_get_batch_size", return_value=8),
            mock.patch.object(
                embeddings_module, "_build_content_item_queryset", return_value=[]
            ),
            mock.patch("apps.content.models.ContentItem"),
        ):
            result = generate_content_item_embeddings()

        # Empty queryset → early return with zeroed counts.
        self.assertEqual(result, {"embedded": 0, "skipped": 0})
        # Legacy branch: signature derived from the legacy model itself.
        get_sig.assert_called_once_with(model=legacy, model_name="local-bge")

    def test_content_item_uses_provider_signature_when_no_legacy_model(self):
        provider = mock.Mock(name="provider")
        provider.model_name = "paid-model"
        provider.signature = "paid-sig"
        with (
            mock.patch.object(
                embeddings_module,
                "_try_get_active_provider",
                return_value=provider,
            ),
            mock.patch.object(
                embeddings_module, "_load_legacy_model_or_none", return_value=None
            ),
            mock.patch.object(embeddings_module, "_get_batch_size", return_value=8),
            mock.patch.object(
                embeddings_module, "_build_content_item_queryset", return_value=[]
            ) as build_qs,
            mock.patch("apps.content.models.ContentItem"),
        ):
            result = generate_content_item_embeddings(content_item_ids=[1, 2])

        self.assertEqual(result, {"embedded": 0, "skipped": 0})
        # Provider branch: the provider's own signature is used verbatim,
        # so the queryset filter receives the provider signature.
        build_qs.assert_called_once()
        self.assertEqual(build_qs.call_args.args[2], "paid-sig")

    def test_sentence_uses_legacy_model_signature_when_present(self):
        legacy = self._legacy_model()
        with (
            mock.patch.object(embeddings_module, "_try_get_active_provider"),
            mock.patch.object(
                embeddings_module, "_load_legacy_model_or_none", return_value=legacy
            ),
            mock.patch.object(
                embeddings_module, "_get_model_name", return_value="local-bge"
            ),
            mock.patch.object(
                embeddings_module,
                "get_current_embedding_signature",
                return_value="local-sig",
            ) as get_sig,
            mock.patch.object(embeddings_module, "_get_batch_size", return_value=8),
            mock.patch.object(
                embeddings_module, "_build_sentence_queryset", return_value=[]
            ),
            mock.patch("apps.content.models.Sentence"),
        ):
            result = generate_sentence_embeddings()

        self.assertEqual(result, {"embedded": 0, "skipped": 0})
        get_sig.assert_called_once_with(model=legacy, model_name="local-bge")

    def test_sentence_uses_provider_signature_when_no_legacy_model(self):
        provider = mock.Mock(name="provider")
        provider.model_name = "paid-model"
        provider.signature = "paid-sig"
        with (
            mock.patch.object(
                embeddings_module,
                "_try_get_active_provider",
                return_value=provider,
            ),
            mock.patch.object(
                embeddings_module, "_load_legacy_model_or_none", return_value=None
            ),
            mock.patch.object(embeddings_module, "_get_batch_size", return_value=8),
            mock.patch.object(
                embeddings_module, "_build_sentence_queryset", return_value=[]
            ) as build_qs,
            mock.patch("apps.content.models.Sentence"),
        ):
            result = generate_sentence_embeddings(content_item_ids=[7])

        self.assertEqual(result, {"embedded": 0, "skipped": 0})
        build_qs.assert_called_once()
        self.assertEqual(build_qs.call_args.args[2], "paid-sig")
