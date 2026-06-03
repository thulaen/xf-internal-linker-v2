"""Convention SimpleTestCase coverage for apps.audit.fix_suggestions.

Both public helpers (`suggest`, `suggest_action_chips`) are pure regex
lookups over a (message, fingerprint, step) blob — no DB, no I/O. These
tests pin the post-GPU-removal behaviour with exact-value asserts so a
future edit cannot silently re-introduce CUDA/VRAM wording or drift the
plain-English fix text.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.audit.fix_suggestions import _GENERIC, suggest, suggest_action_chips


class SuggestTextTests(SimpleTestCase):
    """`suggest()` returns the matching rule's fix text, else the generic hint."""

    def test_when_spacy_missing_then_download_hint(self):
        result = suggest(error_message="Can't find model en_core_web_sm")
        self.assertEqual(
            result,
            "spaCy model is missing. Run "
            "`docker compose exec backend python -m spacy download en_core_web_sm`.",
        )

    def test_when_redis_refused_then_restart_redis_hint(self):
        result = suggest(error_message="Redis connection refused")
        self.assertEqual(result, "Redis is down. Run `docker compose restart redis`.")

    def test_when_thermal_then_host_throttle_hint(self):
        result = suggest(error_message="ThermalThrottleError fired")
        self.assertEqual(
            result,
            "The host is throttling above 85 °C. Pause heavy work for ~5 minutes "
            "via the Quick-Controls panel, or improve case airflow. The job "
            "auto-resumes when the host cools below 75 °C.",
        )

    def test_when_cuda_oom_then_generic_hint(self):
        # The GPU/CUDA rules were removed; CUDA wording now falls through.
        result = suggest(error_message="CUDA out of memory")
        self.assertEqual(result, _GENERIC)

    def test_when_torch_cuda_then_generic_hint(self):
        result = suggest(error_message="torch.cuda not available")
        self.assertEqual(result, _GENERIC)

    def test_when_no_match_then_generic_hint(self):
        result = suggest(error_message="totally unknown failure mode 4271")
        self.assertEqual(result, _GENERIC)

    def test_when_match_on_step_only_then_rule_fires(self):
        # The blob includes step, so a rule can key on it alone.
        result = suggest(error_message="", fingerprint="", step="en_core_web_sm load")
        self.assertEqual(
            result,
            "spaCy model is missing. Run "
            "`docker compose exec backend python -m spacy download en_core_web_sm`.",
        )


class SuggestActionChipsTests(SimpleTestCase):
    """`suggest_action_chips()` returns the matching chip list, else []."""

    def test_when_memory_error_then_lower_batch_chip_only(self):
        chips = suggest_action_chips(error_message="MemoryError in worker")
        self.assertEqual(
            chips,
            [
                {
                    "label": "Lower batch size",
                    "action_url": "/settings/passage-relevance",
                    "tooltip": "Open the embedding batch-size setting.",
                }
            ],
        )

    def test_when_cuda_only_text_then_no_chips(self):
        # The "Reclaim GPU cache" chip was removed and the chip rule now keys
        # on the literal "OOM"/"MemoryError" only. Plain "CUDA out of memory"
        # text (no literal OOM token) therefore yields no chips at all.
        chips = suggest_action_chips(error_message="CUDA out of memory error")
        self.assertEqual(chips, [])

    def test_when_oom_token_then_no_reclaim_gpu_chip(self):
        # An explicit OOM token still matches, but only the batch-size chip
        # survives — the "Reclaim GPU cache" chip was deleted.
        chips = suggest_action_chips(error_message="job hit OOM")
        labels = [chip["label"] for chip in chips]
        self.assertEqual(labels, ["Lower batch size"])

    def test_when_thermal_then_wait_for_cooldown_chip(self):
        chips = suggest_action_chips(error_message="ThermalThrottleError")
        self.assertEqual(
            chips,
            [
                {
                    "label": "Wait for cooldown",
                    "action_url": "",
                    "tooltip": "Host temperature is high. Job auto-resumes when it cools.",
                }
            ],
        )

    def test_when_no_match_then_empty_list(self):
        chips = suggest_action_chips(error_message="nothing actionable here")
        self.assertEqual(chips, [])
