"""Pin the psycopg3 connection-pool recycling defaults in base.py.

The DATABASES pool block gained two recycle knobs so long-running Celery
worker connections do not accumulate psycopg3 ``COMMAND_OK`` / stale-state
errors:

- ``max_lifetime`` defaults to 600 seconds (10 minutes).
- ``max_idle`` defaults to 300 seconds (5 minutes).

``config/settings/test.py`` does not override the DATABASES pool block, but
the loaded value depends on the ``POSTGRES_POOL_MAX_LIFETIME_S`` /
``POSTGRES_POOL_MAX_IDLE_S`` environment variables which CI may set. To pin
the *source default* itself (so a literal mutant changing ``600`` -> ``601``
or dropping a key is killed regardless of the environment), this test asserts
on the exact base.py source text — the same hang-safe, env-independent pattern
used by ``test_pyroscope_sample_rate.py``.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

BASE_SETTINGS = Path(__file__).resolve().parents[1] / "settings" / "base.py"


class DbPoolRecycleConstantsTests(SimpleTestCase):
    def test_max_lifetime_default_is_600_seconds(self) -> None:
        text = BASE_SETTINGS.read_text(encoding="utf-8")
        self.assertIn(
            '"max_lifetime": env.int("POSTGRES_POOL_MAX_LIFETIME_S", default=600)',
            text,
        )

    def test_max_idle_default_is_300_seconds(self) -> None:
        text = BASE_SETTINGS.read_text(encoding="utf-8")
        self.assertIn(
            '"max_idle": env.int("POSTGRES_POOL_MAX_IDLE_S", default=300)',
            text,
        )
