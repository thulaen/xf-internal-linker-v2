"""
Base Django settings for XF Internal Linker V2.

All shared settings live here. Environment-specific settings
(development.py, production.py) import from this file and override.

Never import from this file directly — always use development.py or production.py.
"""

from pathlib import Path

import environ

# Build paths relative to the backend/ directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read environment variables from .env file
env = environ.Env()
environ.Env.read_env(BASE_DIR.parent / ".env")


# ── Django Core ──────────────────────────────────────────────────

SECRET_KEY = env("DJANGO_SECRET_KEY")

DJANGO_APPS = [
    # unfold must come BEFORE django.contrib.admin to override the admin UI
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "channels",
    "django_celery_beat",
    "django_celery_results",
    "django_filters",
    "drf_spectacular",
    "pgvector.django",
]

LOCAL_APPS = [
    "apps.core",
    "apps.content",
    "apps.suggestions",
    "apps.pipeline",
    "apps.analytics",
    "apps.webhooks",
    "apps.audit",
    "apps.graph",
    "apps.plugins",
    "apps.sync",
    "apps.api",
    "apps.diagnostics",
    "apps.notifications",
    "apps.knowledge_graph",
    "apps.health",
    "apps.cooccurrence",
    "apps.crawler",
    "apps.benchmarks",
    "apps.realtime",
    # Phase OF — Operations Feed.
    "apps.ops_feed",
    # PR-B — Scheduled Updates orchestrator (1pm-11pm serial runner).
    "apps.scheduled_updates",
    # PR-C — Source-layer helpers (token bucket, backoff, bloom, HLL, etc).
    "apps.sources",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Must be before CommonMiddleware
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Rolling per-user "last seen" heartbeat for the dashboard
    # whos-on-shift widget. Runs after AuthenticationMiddleware so
    # `request.user` is resolved. Silent no-op for anonymous requests.
    "apps.core.middleware.UserActivityMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ASGI application for Django Channels (WebSockets)
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"


# ── Database — PostgreSQL 17 with pgvector ───────────────────────

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="xf_linker"),
        "USER": env("POSTGRES_USER", default="xf_linker_user"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="postgres"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

# Use psycopg 3 (psycopg, not psycopg2)
# This is set via the ENGINE but we document it here
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ── Redis + Caching ───────────────────────────────────────────────

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default="redis://redis:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "xfl_v2",
        "TIMEOUT": env.int("CACHE_TTL_PIPELINE", default=3600),
    }
}

# Cache TTLs (seconds)
CACHE_TTL_PIPELINE = env.int("CACHE_TTL_PIPELINE", default=3600)
CACHE_TTL_XENFORO_API = env.int("CACHE_TTL_XENFORO_API", default=900)
CACHE_TTL_GSC = env.int("CACHE_TTL_GSC", default=21600)
CACHE_TTL_PAGERANK = env.int("CACHE_TTL_PAGERANK", default=3600)


# ── Django Channels (WebSockets) ──────────────────────────────────

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("REDIS_CHANNELS_URL", default="redis://redis:6379/3")],
        },
    }
}


# ── Celery ────────────────────────────────────────────────────────

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/2")
CELERY_RESULT_BACKEND = "django-db"  # Store results in PostgreSQL
CELERY_CACHE_BACKEND = "default"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_WORKER_CONCURRENCY = env.int("CELERY_WORKER_CONCURRENCY", default=2)

# Task routing to named queues
CELERY_TASK_ROUTES = {
    "apps.pipeline.tasks.*": {"queue": "pipeline"},
    "apps.content.tasks.*": {"queue": "embeddings"},
}

# ── Stored Periodic Schedule Seeds ────────────────────────────────
# Nightly auto-sync from XenForo API at 02:00 UTC.
# Only runs when XENFORO_API_KEY and XENFORO_BASE_URL are configured.
# The C# scheduler may read these django_celery_beat rows directly during migration.

from .celery_schedules import CELERY_BEAT_SCHEDULE  # noqa: E402, F401

# ── C++ Native Extensions ────────────────────────────────────────

# When True (default), all C++ pybind11 extensions are imported and used.
# When False, extensions raise RuntimeError — no silent Python fallback.
# Set False ONLY in unit tests that mock or skip extension calls.
USE_NATIVE_EXTENSIONS = env.bool("USE_NATIVE_EXTENSIONS", default=True)

# Self-pruning interval: prune stale model snapshots, passage embeddings for
# deleted pages, particle filter history, and cache entries older than this.
PRUNE_INTERVAL_DAYS = env.int("PRUNE_INTERVAL_DAYS", default=84)


# ── Django Unfold Admin ───────────────────────────────────────────

UNFOLD = {
    "SITE_TITLE": "XF Internal Linker",
    "SITE_HEADER": "XF Internal Linker V2",
    "SITE_URL": "/",
    "SITE_ICON": None,
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "STYLES": [],
    "SCRIPTS": [],
    "COLORS": {
        "primary": {
            "50": "232 240 254",
            "100": "211 227 253",
            "200": "194 231 255",
            "300": "138 180 248",
            "400": "66 133 244",
            "500": "26 115 232",
            "600": "11 87 208",
            "700": "0 74 119",
            "800": "0 29 53",
            "900": "0 20 37",
            "950": "0 10 20",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Content",
                "separator": False,
                "items": [
                    {
                        "title": "Content Items",
                        "icon": "article",
                        "link": "/admin/content/contentitem/",
                    },
                    {
                        "title": "Scope Items",
                        "icon": "folder_open",
                        "link": "/admin/content/scopeitem/",
                    },
                    {
                        "title": "Posts",
                        "icon": "edit_note",
                        "link": "/admin/content/post/",
                    },
                    {
                        "title": "Sentences",
                        "icon": "format_list_bulleted",
                        "link": "/admin/content/sentence/",
                    },
                ],
            },
            {
                "title": "Suggestions",
                "separator": False,
                "items": [
                    {
                        "title": "All Suggestions",
                        "icon": "link",
                        "link": "/admin/suggestions/suggestion/",
                    },
                    {
                        "title": "Pipeline Runs",
                        "icon": "play_circle",
                        "link": "/admin/suggestions/pipelinerun/",
                    },
                    {
                        "title": "Diagnostics",
                        "icon": "bug_report",
                        "link": "/admin/suggestions/pipelinediagnostic/",
                    },
                ],
            },
            {
                "title": "Analytics",
                "separator": False,
                "items": [
                    {
                        "title": "Search Metrics",
                        "icon": "search",
                        "link": "/admin/analytics/searchmetric/",
                    },
                    {
                        "title": "Impact Reports",
                        "icon": "trending_up",
                        "link": "/admin/analytics/impactreport/",
                    },
                ],
            },
            {
                "title": "Links & Graph",
                "separator": False,
                "items": [
                    {
                        "title": "Broken Links",
                        "icon": "link_off",
                        "link": "/admin/graph/brokenlink/",
                    },
                    {
                        "title": "Existing Links",
                        "icon": "hub",
                        "link": "/admin/graph/existinglink/",
                    },
                ],
            },
            {
                "title": "Audit",
                "separator": False,
                "items": [
                    {
                        "title": "Audit Trail",
                        "icon": "history",
                        "link": "/admin/audit/auditentry/",
                    },
                    {
                        "title": "Reviewer Scorecards",
                        "icon": "scorecard",
                        "link": "/admin/audit/reviewerscorecard/",
                    },
                    {
                        "title": "Error Log",
                        "icon": "error_outline",
                        "link": "/admin/audit/errorlog/",
                    },
                ],
            },
            {
                "title": "Plugins",
                "separator": False,
                "items": [
                    {
                        "title": "Installed Plugins",
                        "icon": "extension",
                        "link": "/admin/plugins/plugin/",
                    },
                ],
            },
            {
                "title": "Configuration",
                "separator": True,
                "items": [
                    {
                        "title": "App Settings",
                        "icon": "settings",
                        "link": "/admin/core/appsetting/",
                    },
                ],
            },
        ],
    },
}


# ── Django REST Framework ─────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Realtime ops dashboard: a single logged-in operator easily makes
        # 200-500 req/hour under normal use (timer polls + page loads +
        # realtime widgets). Anonymous traffic during startup is a burst
        # of checks before login resolves, so anon also needs headroom.
        # Per-endpoint scoped throttles below still cap abusive actions.
        "anon": "2000/hour",
        "user": "20000/hour",
        # Per-endpoint scoped rates (see apps/api/throttles.py)
        "graph_rebuild": "6/hour",
        "weight_recalc": "12/hour",
        "cooccurrence_compute": "6/hour",
        "import_trigger": "2/minute",
        "ml_embed": "5/minute",
        "challenger_eval": "1/minute",
        "settings_write": "10/minute",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


# ── CORS ─────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:4200", "http://127.0.0.1:4200"],
)
CORS_ALLOW_CREDENTIALS = True

# CSRF Settings for cross-origin frontend
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
]
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"


# ── Password Validation ───────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ── Internationalization ──────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ── Static and Media Files ────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ── XenForo API (read-only) ───────────────────────────────────────

XENFORO_BASE_URL = env("XENFORO_BASE_URL", default="")
XENFORO_API_KEY = env("XENFORO_API_KEY", default="")
XENFORO_WEBHOOK_SECRET = env("XENFORO_WEBHOOK_SECRET", default="")


# ── WordPress API (read-only, optional) ──────────────────────────

WORDPRESS_BASE_URL = env("WORDPRESS_BASE_URL", default="")
WORDPRESS_USERNAME = env("WORDPRESS_USERNAME", default="")
WORDPRESS_APP_PASSWORD = env("WORDPRESS_APP_PASSWORD", default="")


# All heavy I/O and CPU tasks are now owned by Celery (Python/C++).
# The legacy C# HttpWorker has been decommissioned.

RUNTIME_PROGRESS_STREAM_PREFIX = (
    env("RUNTIME_PROGRESS_STREAM_PREFIX", default="runtime:progress").strip()
    or "runtime:progress"
)
RUNTIME_PROGRESS_STREAM_BLOCK_MS = max(
    env.int("RUNTIME_PROGRESS_STREAM_BLOCK_MS", default=5000), 1000
)
SCHEDULER_CONTROL_TOKEN = env("SCHEDULER_CONTROL_TOKEN", default="").strip()
CELERY_BEAT_RUNTIME_ENABLED = env.bool("CELERY_BEAT_RUNTIME_ENABLED", default=True)
LOCAL_VERIFICATION_BOOTSTRAP_ENABLED = env.bool(
    "LOCAL_VERIFICATION_BOOTSTRAP_ENABLED", default=False
)


# ── ML / AI Settings ─────────────────────────────────────────────

ML_PERFORMANCE_MODE = env("ML_PERFORMANCE_MODE", default="BALANCED")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="BAAI/bge-m3")
EMBEDDING_BATCH_SIZE = env.int("EMBEDDING_BATCH_SIZE", default=32)

# ── GPU Self-Limiting ─────────────────────────────────────────────
# Mode-dependent VRAM fractions.  Percentages are relative to detected
# VRAM — they scale automatically with GPU upgrades.
# See docs/PERFORMANCE.md §6 for the three-layer GPU protection scheme.
CUDA_MEMORY_FRACTION_SAFE = env.float("CUDA_MEMORY_FRACTION_SAFE", default=0.25)
CUDA_MEMORY_FRACTION_HIGH = env.float("CUDA_MEMORY_FRACTION_HIGH", default=0.80)
GPU_TEMP_CEILING_C = env.int("GPU_TEMP_CEILING_C", default=90)
GPU_TEMP_RESUME_C = env.int("GPU_TEMP_RESUME_C", default=80)
SPACY_MODEL = env("SPACY_MODEL", default="en_core_web_sm")

# Pipeline guardrails (non-negotiable product rules)
MAX_LINKS_PER_HOST_THREAD = 3
HOST_SCAN_WORD_LIMIT = min(env.int("HOST_SCAN_WORD_LIMIT", default=1200), 2000)


# ── Error Tracking (GlitchTip / Sentry-compatible) ──────────────────────────
# Self-hosted GlitchTip running in Docker reuses this project's PostgreSQL and
# Redis. Set ERROR_TRACKING_DSN or GLITCHTIP_DSN in .env to enable.
# When both are empty, every call here is a no-op.
#
# AGENTS: Never remove or comment out this block — it is the only error
# tracking for both Python exceptions and pybind11 C++ exceptions.
#
# ERROR_TRACKING_DSN is the canonical name; GLITCHTIP_DSN remains as a legacy
# alias so a future switch to paid Sentry is one env var, zero code changes.
# Phase GT of the approved master plan.
_TRACKING_DSN = env("ERROR_TRACKING_DSN", default="") or env(
    "GLITCHTIP_DSN", default=""
)
if _TRACKING_DSN:
    import socket as _socket

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_TRACKING_DSN,
        release=env("APP_VERSION", default="dev"),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        environment=env("DJANGO_ENV", default="production"),
        send_default_pii=False,
    )
    # Tag every captured event with the host node identity so errors from
    # future worker/K8s/Lightsail/slave nodes stay attributable. Safe to
    # override via NODE_ID / NODE_ROLE env vars per container.
    sentry_sdk.set_tag("node_id", env("NODE_ID", default=_socket.gethostname()))
    sentry_sdk.set_tag("node_role", env("NODE_ROLE", default="primary"))

# ── drf-spectacular (OpenAPI schema) ────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "XF Internal Linker API",
    "DESCRIPTION": "REST API for the XenForo internal linking tool.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# ── Logging ───────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# ── WebAuthn / Passkey ────────────────────────────────────────────
# RP ID is the domain the browser scopes credentials to. For local
# development we use "localhost" — browsers allow WebAuthn over plain
# HTTP only when the origin is localhost. In production this must be
# the bare hostname (no port, no scheme) of the public site.
#
# RP_ORIGIN is the full origin (scheme + host [+ port]) the browser
# sends on the WebAuthn request. Must match what the user types into
# the address bar.
WEBAUTHN_RP_ID = env("WEBAUTHN_RP_ID", default="localhost")
WEBAUTHN_RP_NAME = env("WEBAUTHN_RP_NAME", default="XF Internal Linker")
WEBAUTHN_RP_ORIGIN = env("WEBAUTHN_RP_ORIGIN", default="http://localhost")
