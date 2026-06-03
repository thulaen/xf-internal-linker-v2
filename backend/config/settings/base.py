"""
Base Django settings for XF Internal Linker V2.

All shared settings live here. Environment-specific settings
(development.py, production.py) import from this file and override.

Never import from this file directly — always use development.py or production.py.
"""

import logging
from pathlib import Path

import environ

# Build paths relative to the backend/ directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read environment variables from .env file
env = environ.Env()
environ.Env.read_env(BASE_DIR.parent / ".env")


class _GracefulTelemetryExporter:
    """Convert telemetry send failures into normal failed-export results."""

    def __init__(self, exporter, *, failure_result):
        self._exporter = exporter
        self._failure_result = failure_result
        self._logger = logging.getLogger("config.telemetry")

    def export(self, payload, *args, **kwargs):
        try:
            return self._exporter.export(payload, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - telemetry must not break app work.
            self._logger.debug(
                "Telemetry export skipped after exporter failure: %s", exc
            )
            return self._failure_result

    def force_flush(self, *args, timeout_millis=30_000, **kwargs):
        try:
            return self._exporter.force_flush(
                *args,
                timeout_millis=timeout_millis,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 - shutdown flush must stay graceful.
            self._logger.debug(
                "Telemetry flush skipped after exporter failure: %s", exc
            )
            return False

    def shutdown(self, *args, **kwargs):
        try:
            return self._exporter.shutdown(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - shutdown must never mask command exit.
            self._logger.debug(
                "Telemetry shutdown skipped after exporter failure: %s", exc
            )
            return None

    def __getattr__(self, name):
        return getattr(self._exporter, name)


def _env_float(name: str, *, default: float, minimum: float) -> float:
    try:
        value = float(env(name, default=str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


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
    "apps.observability",
    "apps.notifications",
    "apps.knowledge_graph",
    "apps.health",
    "apps.cooccurrence",
    "apps.crawler",
    "apps.benchmarks",
    "apps.realtime",
    # Phase OF — Operations Feed.
    "apps.ops_feed",
    # Agent work queue. Tracks agent claims, repair attempts, and rollback signals.
    "apps.work_queue",
    # PR-B — Scheduled Updates orchestrator (11am-11pm serial runner).
    "apps.scheduled_updates",
    # PR-C — Source-layer helpers (token bucket, backoff, bloom, HLL, etc).
    "apps.sources",
    # Phase 6.5 — Offline training stack (picks #41-46: L-BFGS-B, TPE,
    # Cosine Annealing, LambdaLoss, SWA, OHEM). Per the Anti-Spaghetti
    # Charter (52-pick plan) this is the single sanctioned new-app
    # exception in the completion phase.
    "apps.training",
    # 2026-05-09 — Auto-issues. Single store for issues surfaced by
    # GlitchTip + Pyroscope + agent finds. Reuses the running postgres;
    # the C++ daily-picker (spec: docs/CPP-DAILY-ISSUE-PICKER-SPEC.md)
    # writes here. Read by every agent at session start via
    # `manage.py print_open_issues`.
    "apps.auto_issues",
    # 2026-05-15 — Paper trail. Separate table that captures every
    # deliberately-deferred work item with a high-detail abstract.
    # Distinct from auto_issues (which tracks discovered problems).
    # Read by every agent at session start via
    # `manage.py print_open_paper_trail`. Dedup is backed by the C++
    # extension `papertrail_dedup` (MinHash + LSH).
    "apps.paper_trail",
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
        # Phase 2.13 — psycopg 3 native connection pool. Replaces the old
        # CONN_MAX_AGE per-request handshake with a always-warm pool of
        # ``min_size`` connections plus on-demand growth up to ``max_size``.
        # Typical 3-5x throughput improvement on the API layer because
        # every request reuses a healthy connection instead of paying the
        # ~5 ms handshake. CONN_MAX_AGE is intentionally NOT set — the
        # pool manages connection lifetime end-to-end.
        # Citation: psycopg 3 docs §6 "Connection pool".
        "OPTIONS": {
            "connect_timeout": 10,
            "pool": {
                "min_size": env.int("POSTGRES_POOL_MIN_SIZE", default=4),
                "max_size": env.int("POSTGRES_POOL_MAX_SIZE", default=20),
                "timeout": env.int("POSTGRES_POOL_TIMEOUT_S", default=30),
                # Force connection recycling so psycopg3 COMMAND_OK / stale-state
                # errors don't accumulate on long-running worker connections.
                # max_lifetime=600s prevents any one connection from staying open
                # longer than 10 minutes. max_idle=300s closes idle connections after
                # 5 minutes so pool slots don't stay open through Celery idle periods.
                # Citation: psycopg3 docs §6.4 "Pool configuration".
                "max_lifetime": env.int("POSTGRES_POOL_MAX_LIFETIME_S", default=600),
                "max_idle": env.int("POSTGRES_POOL_MAX_IDLE_S", default=300),
            },
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
        # Phase 4.9 — synchronous compression audit. Each call walks
        # ~10k rows of zlib compression and pins the request worker
        # for 30-120 s; rate-limit so an accidentally-mashed button
        # (or compromised token) can't DoS the worker pool.
        "compression_audit_run": "3/hour",
        # Phase 4.11 — benchmark trigger queues a 5-15 minute Celery
        # job; cap at 2/hour so a flood of triggers can't backlog the
        # benchmark queue. Cert run-now is a cheaper aggregation over
        # the latest BenchmarkRun (~1-2 s) so it gets a higher cap.
        "benchmark_run_trigger": "2/hour",
        "performance_cert_run": "6/hour",
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


# All heavy I/O and CPU tasks are owned by Celery (Python/C++).
# The legacy HTTP worker (decommissioned 2026-04-12) is no longer running.

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
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="text-embedding-3-small")
EMBEDDING_BATCH_SIZE = env.int("EMBEDDING_BATCH_SIZE", default=32)
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


def _observability_host_resolves(raw_url: str) -> bool:
    """Return true when an optional observability endpoint is reachable."""

    if env("OBSERVABILITY_SKIP_UNRESOLVED_ENDPOINTS", default="1") == "0":
        return True
    if not raw_url:
        return False

    import socket
    from urllib.parse import urlparse

    parsed = urlparse(raw_url)
    host = parsed.hostname
    if not host:
        return True
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


if _TRACKING_DSN and _observability_host_resolves(_TRACKING_DSN):
    import socket as _socket

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_TRACKING_DSN,
        release=env("APP_VERSION", default="dev"),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        # 0.3 = capture timing for 30 % of every Django view + Celery task
        # as a transaction so GlitchTip's Performance tab has data. Bumped
        # from 0.1 (the original conservative default) on 2026-05-09.
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", default="1.0")),
        # Profiling — captures Python stack samples on traced transactions
        # and ships them as flamegraphs to GlitchTip's Profiles tab. This
        # REPLACES the pyroscope-io shipping path (ISS-103) which the
        # Pyroscope OSS 1.9 server does not index. Same DSN, same auth,
        # same dashboard — one less moving part.
        profiles_sample_rate=float(env("SENTRY_PROFILES_SAMPLE_RATE", default="1.0")),
        environment=env("DJANGO_ENV", default="production"),
        send_default_pii=False,
    )
    # Tag every captured event with the host node identity so errors from
    # future worker/K8s/Lightsail/slave nodes stay attributable. Safe to
    # override via NODE_ID / NODE_ROLE env vars per container.
    sentry_sdk.set_tag("node_id", env("NODE_ID", default=_socket.gethostname()))
    sentry_sdk.set_tag("node_role", env("NODE_ROLE", default="primary"))

# ── Pyroscope continuous profiling ─────────────────────────────────────
# Re-enabled 2026-05-09: upgrading the agent from 0.8.7 → 1.0.6 fixed
# ISS-103. The 0.8.x series spoke a legacy push protocol that Pyroscope
# OSS 1.x silently dropped; 1.0.6 speaks the pprof-format protocol the
# modern server expects. Default-on whenever PYROSCOPE_SERVER_ADDRESS is
# set (which docker-compose sets for backend + Celery containers). If a
# future agent regression breaks ingest again, set PYROSCOPE_ENABLED=0
# in `.env` to disable; Sentry profiling continues to cover the same
# functional need via GlitchTip's Profiles tab.
_PYROSCOPE_ADDR = env("PYROSCOPE_SERVER_ADDRESS", default="")
_PYROSCOPE_ENABLED = env("PYROSCOPE_ENABLED", default="1") != "0"
if (
    _PYROSCOPE_ADDR
    and _PYROSCOPE_ENABLED
    and _observability_host_resolves(_PYROSCOPE_ADDR)
):
    try:
        import pyroscope  # type: ignore[import-not-found]

        pyroscope.configure(
            application_name=env(
                "PYROSCOPE_APPLICATION_NAME", default="xf-linker-backend"
            ),
            server_address=_PYROSCOPE_ADDR,
            sample_rate=env.int("PYROSCOPE_SAMPLE_RATE", default=250),
            tags={
                "node_role": env("NODE_ROLE", default="primary"),
                "node_id": env("NODE_ID", default="primary"),
            },
        )
    except ImportError:
        # pyroscope-io optional at install time — silently skip when missing
        # (e.g. dev shells that pip-install a slim subset of requirements).
        pass

# ── OpenTelemetry — vendor-neutral traces / metrics / logs ─────────────
# Opt-in via OTEL_EXPORTER_OTLP_ENDPOINT (set in docker-compose for the
# backend + Celery containers, pointing at `http://otel-collector:4318`).
# When unset, every call here is a no-op. The collector fans the data
# out to GlitchTip OTLP / Prometheus scrape / stdout (see otelcol-config.yaml).
#
# What this captures that the Sentry SDK doesn't:
#  - DB query timing per-statement (psycopg auto-instrumentation),
#  - Redis operation timing (broker + cache),
#  - HTTP client spans for sync `requests` and async `httpx`,
#  - Celery task spans with parent/child trace correlation,
#  - Log records get trace_id stamped so logs link to the trace UI.
#
# Sample rate matches the Sentry tracing config — 0.3 in dev — set via
# OTEL_TRACES_SAMPLER + OTEL_TRACES_SAMPLER_ARG in compose.
_OTEL_ENDPOINT = env("OTEL_EXPORTER_OTLP_ENDPOINT", default="")
_OTEL_EXPORT_TIMEOUT_SECONDS = _env_float(
    "OTEL_EXPORTER_OTLP_TIMEOUT",
    default=2.0,
    minimum=0.1,
)
# Skip OTel auto-instrumentation during `manage.py test` runs — the
# psycopg span recorder adds ~5 ms per query, which combined with the
# test DB's `statement_timeout` makes some long-running tests trip the
# limit. Tests already mock external behaviour and don't need traces.
import sys as _sys

_TEST_RUN_ARGS = {"test", "pytest"}
_IS_TEST_RUN = (
    any(Path(arg).name in _TEST_RUN_ARGS for arg in _sys.argv)
    or "pytest" in _sys.modules
    or env("DJANGO_TEST_RUN", default="0") == "1"
)
if _OTEL_ENDPOINT and not _IS_TEST_RUN and _observability_host_resolves(_OTEL_ENDPOINT):
    try:
        from opentelemetry import trace as _otel_trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExportResult

        _otel_resource = Resource.create(
            {
                "service.name": env(
                    "PYROSCOPE_APPLICATION_NAME", default="xf-linker-backend"
                ),
                "service.version": env("APP_VERSION", default="dev"),
                "deployment.environment": env("DJANGO_ENV", default="production"),
                "node.role": env("NODE_ROLE", default="primary"),
                "node.id": env("NODE_ID", default="primary"),
            }
        )
        _otel_provider = TracerProvider(resource=_otel_resource)
        _otel_provider.add_span_processor(
            BatchSpanProcessor(
                _GracefulTelemetryExporter(
                    OTLPSpanExporter(
                        endpoint=f"{_OTEL_ENDPOINT}/v1/traces",
                        timeout=_OTEL_EXPORT_TIMEOUT_SECONDS,
                    ),
                    failure_result=SpanExportResult.FAILURE,
                )
            )
        )
        _otel_trace.set_tracer_provider(_otel_provider)

        # Auto-instrumentation. Each call adds spans without source edits.
        # `is_sql_commentor_enabled=False` keeps SQL bodies out of trace
        # attributes (the collector already scrubs `db.statement`).
        DjangoInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        PsycopgInstrumentor().instrument(enable_commenter=False)
        RedisInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        LoggingInstrumentor().instrument(set_logging_format=True)

        # System metrics — CPU / RAM / GC / open file descriptors. Sent
        # to the OTel collector's metrics pipeline → Prometheus scrape.
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.instrumentation.system_metrics import (
                SystemMetricsInstrumentor,
            )
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import (
                MetricExportResult,
                PeriodicExportingMetricReader,
            )
            from opentelemetry import metrics as _otel_metrics

            _metric_reader = PeriodicExportingMetricReader(
                _GracefulTelemetryExporter(
                    OTLPMetricExporter(
                        endpoint=f"{_OTEL_ENDPOINT}/v1/metrics",
                        timeout=_OTEL_EXPORT_TIMEOUT_SECONDS,
                    ),
                    failure_result=MetricExportResult.FAILURE,
                ),
                export_interval_millis=30_000,
            )
            _meter_provider = MeterProvider(
                resource=_otel_resource, metric_readers=[_metric_reader]
            )
            _otel_metrics.set_meter_provider(_meter_provider)
            SystemMetricsInstrumentor().instrument()
        except ImportError:
            pass
    except ImportError:
        # OTel packages optional — silently skip when not installed.
        pass

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


# ``__all__`` declares the public surface of this module.  Downstream
# settings files (development.py / production.py / test.py / ci.py) do
# ``from .base import *`` to inherit every shared setting.  Defining
# ``__all__`` here satisfies SonarSource's ``python:S2208`` documented
# exception clause: the rule does not raise when the imported module
# declares ``__all__`` (see https://rules.sonarsource.com/python/RSPEC-2208).
# Written as an explicit static list of strings because SonarSource's
# Python analyzer recognises a literal collection but does not honour
# a dynamically-computed ``__all__``.  When a new public setting is
# added to this file, append its name below; the regression test at
# ``backend/config/tests/test_settings_no_wildcard.py`` keeps the
# inherited contract honest.
__all__ = [
    "ASGI_APPLICATION",
    "AUTH_PASSWORD_VALIDATORS",
    "BASE_DIR",
    "CACHES",
    "CACHE_TTL_GSC",
    "CACHE_TTL_PAGERANK",
    "CACHE_TTL_PIPELINE",
    "CACHE_TTL_XENFORO_API",
    "CELERY_ACCEPT_CONTENT",
    "CELERY_BEAT_RUNTIME_ENABLED",
    "CELERY_BEAT_SCHEDULE",
    "CELERY_BEAT_SCHEDULER",
    "CELERY_BROKER_URL",
    "CELERY_CACHE_BACKEND",
    "CELERY_RESULT_BACKEND",
    "CELERY_RESULT_SERIALIZER",
    "CELERY_TASK_ROUTES",
    "CELERY_TASK_SERIALIZER",
    "CELERY_TIMEZONE",
    "CELERY_WORKER_CONCURRENCY",
    "CHANNEL_LAYERS",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "CSRF_COOKIE_SAMESITE",
    "CSRF_TRUSTED_ORIGINS",
    "DATABASES",
    "DEFAULT_AUTO_FIELD",
    "DJANGO_APPS",
    "EMBEDDING_BATCH_SIZE",
    "EMBEDDING_MODEL",
    "HOST_SCAN_WORD_LIMIT",
    "INSTALLED_APPS",
    "LANGUAGE_CODE",
    "LOCAL_APPS",
    "LOCAL_VERIFICATION_BOOTSTRAP_ENABLED",
    "LOGGING",
    "MAX_LINKS_PER_HOST_THREAD",
    "MEDIA_ROOT",
    "MEDIA_URL",
    "MIDDLEWARE",
    "ML_PERFORMANCE_MODE",
    "PRUNE_INTERVAL_DAYS",
    "REDIS_URL",
    "REST_FRAMEWORK",
    "ROOT_URLCONF",
    "RUNTIME_PROGRESS_STREAM_BLOCK_MS",
    "RUNTIME_PROGRESS_STREAM_PREFIX",
    "SCHEDULER_CONTROL_TOKEN",
    "SECRET_KEY",
    "SESSION_COOKIE_SAMESITE",
    "SPACY_MODEL",
    "SPECTACULAR_SETTINGS",
    "STATICFILES_DIRS",
    "STATIC_ROOT",
    "STATIC_URL",
    "TEMPLATES",
    "THIRD_PARTY_APPS",
    "TIME_ZONE",
    "UNFOLD",
    "USE_I18N",
    "USE_NATIVE_EXTENSIONS",
    "USE_TZ",
    "WEBAUTHN_RP_ID",
    "WEBAUTHN_RP_NAME",
    "WEBAUTHN_RP_ORIGIN",
    "WORDPRESS_APP_PASSWORD",
    "WORDPRESS_BASE_URL",
    "WORDPRESS_USERNAME",
    "WSGI_APPLICATION",
    "XENFORO_API_KEY",
    "XENFORO_BASE_URL",
    "XENFORO_WEBHOOK_SECRET",
    "env",
]
