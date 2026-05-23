# pylint: disable=undefined-variable
"""
Production settings for XF Internal Linker V2.

Used when deploying to a web server.
DEBUG=False, strict security, HTTPS required.

The file-level ``# pylint: disable=undefined-variable`` directive on
line 1 acknowledges that names like ``MIDDLEWARE`` are re-exported from
``config.settings.base`` via the ``from .base import *`` star-import.
PyLint cannot follow the star-import + ``__all__`` re-export idiom
statically, so the only correct shape is a documented file-level
disable; the runtime contract is pinned by
``backend/config/tests/test_settings_no_wildcard.py``.
"""

from .base import *  # noqa: F401, F403
import environ
# Wildcard import is safe here because base.py declares ``__all__`` at the
# bottom of the file. SonarSource's ``python:S2208`` documented exception
# clause does not raise when the source module declares ``__all__``.

env = environ.Env()

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])

# ── Security headers ──────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Tell Django to trust the X-Forwarded-Proto header set by nginx (see
# nginx/nginx.prod.conf "proxy_set_header X-Forwarded-Proto https"). Without
# this, request.is_secure() returns False inside the container and
# request.build_absolute_uri() emits http:// URLs — which Google's OAuth
# rejects as "redirect_uri_mismatch" because we registered the https://
# variant. Pair this with USE_X_FORWARDED_HOST so build_absolute_uri()
# also picks up the public host instead of the internal Docker hostname.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# HSTS + cookie-secure + SSL redirect default to True (HTTPS-only),
# but each can be disabled via env for a local prod-mode test over HTTP
# (e.g. `docker compose --env-file .env up`).
# A real HTTPS deployment keeps the defaults.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=True)

# ── Static files via WhiteNoise ───────────────────────────────────
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Email: real SMTP in production ────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")

# ── CORS: explicit origins only in production ─────────────────────
CORS_ALLOW_ALL_ORIGINS = False
