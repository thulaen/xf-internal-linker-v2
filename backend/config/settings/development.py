# pylint: disable=undefined-variable
"""
Development settings for XF Internal Linker V2.

Used when running locally via Docker Compose. Enables debug mode by
default (override via the DJANGO_DEBUG env var), relaxes security, turns
on verbose logging, and does not require HTTPS.

The file-level ``# pylint: disable=undefined-variable`` directive on
line 1 acknowledges that names like ``LOGGING``, ``MIDDLEWARE``, and
``ALLOWED_HOSTS`` are re-exported from ``config.settings.base`` via the
``from .base import *`` star-import. PyLint cannot follow the star-import
+ ``__all__`` re-export idiom statically, so the only correct shape is
a documented file-level disable; the runtime contract is pinned by
``backend/config/tests/test_settings_no_wildcard.py``.
"""

from .base import *  # noqa: F401, F403
# Wildcard import is safe here because base.py declares ``__all__`` at the
# bottom of the file. SonarSource's ``python:S2208`` documented exception
# clause does not raise when the source module declares ``__all__``.
# ``backend/config/tests/test_settings_no_wildcard.py`` pins the contract.

import os

# Env-driven so an operator can opt out of debug mode in a dev container
# without editing this file. Defaults to enabled because this file IS the
# development settings module.
DEBUG = os.environ.get("DJANGO_DEBUG", "1") != "0"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "backend", "*"]

# ── Email: print to console during development ────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── Django Debug Toolbar (optional, only in dev) ─────────────────
# Uncomment if you add debug-toolbar to requirements-dev.txt
# INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
# MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405
# INTERNAL_IPS = ["127.0.0.1"]

# ── More verbose logging in development ───────────────────────────
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405

# ── CORS: allow Angular dev server ───────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True  # Only safe in dev — never in production!

# ── CSRF: trust the Angular dev server origin ─────────────────────
CSRF_TRUSTED_ORIGINS = ["http://localhost:4200", "http://127.0.0.1:4200"]

# ── Celery: eager mode for debugging (tasks run synchronously) ────
# Uncomment to debug tasks without Redis:
# CELERY_TASK_ALWAYS_EAGER = True
# CELERY_TASK_EAGER_PROPAGATES = True
