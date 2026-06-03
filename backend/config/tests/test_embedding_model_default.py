"""Pin the EMBEDDING_MODEL source default in base.py.

The base default was changed from a self-hosted model name to the OpenAI
``text-embedding-3-small`` model. ``config/settings/test.py`` overrides
``EMBEDDING_MODEL`` to ``"BAAI/bge-m3"`` for the test run, so a settings-loaded
assertion cannot observe the base default. To pin the *source default* itself
(killing a literal mutant on the model string) this test asserts on the exact
base.py source text — the same hang-safe, env-independent pattern used by
``test_pyroscope_sample_rate.py``.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

BASE_SETTINGS = Path(__file__).resolve().parents[1] / "settings" / "base.py"


class EmbeddingModelDefaultTests(SimpleTestCase):
    def test_embedding_model_default_is_text_embedding_3_small(self) -> None:
        text = BASE_SETTINGS.read_text(encoding="utf-8")
        self.assertIn(
            'EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="text-embedding-3-small")',
            text,
        )
