"""
Development settings for XF Internal Linker V2.

Used when running locally via Docker Compose.
DEBUG=True, relaxed security, verbose logging, no HTTPS required.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

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
