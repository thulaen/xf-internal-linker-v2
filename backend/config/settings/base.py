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
        "PASSWORD": env("POSTGRES_PASSWORD", default="changeme"),
        "HOST": env("POSTGRES_HOST", default="postgres"),
        "PORT": env("POSTGRES_PORT", default="5432"),
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
        "LOCATION": env("REDIS_URL", default="redis://redis:6379/1"),
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
            "hosts": [env("REDIS_URL", default="redis://redis:6379/3")],
        },
    }
}


# ── Celery ────────────────────────────────────────────────────────

CELERY_BROKER_URL = env("REDIS_URL", default="redis://redis:6379/2")
CELERY_RESULT_BACKEND = "django-db"  # Store results in PostgreSQL
CELERY_CACHE_BACKEND = "default"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_WORKER_CONCURRENCY = env.int("CELERY_WORKER_CONCURRENCY", default=4)

# Task routing to named queues
CELERY_TASK_ROUTES = {
    "apps.pipeline.tasks.*": {"queue": "pipeline"},
    "apps.content.tasks.*": {"queue": "embeddings"},
}

# ── Celery Beat — Scheduled Tasks ─────────────────────────────────
# Nightly auto-sync from XenForo API at 02:00 UTC.
# Only runs when XENFORO_API_KEY and XENFORO_BASE_URL are configured.
# Override schedule via Django admin → Periodic Tasks (django-celery-beat).

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "nightly-xenforo-sync": {
        "task": "pipeline.import_content",
        "schedule": crontab(hour=2, minute=0),
        "kwargs": {"source": "api", "mode": "full"},
        "options": {"queue": "pipeline"},
    },
}


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
                    {"title": "Content Items", "icon": "article", "link": "/admin/content/contentitem/"},
                    {"title": "Scope Items", "icon": "folder_open", "link": "/admin/content/scopeitem/"},
                    {"title": "Posts", "icon": "edit_note", "link": "/admin/content/post/"},
                    {"title": "Sentences", "icon": "format_list_bulleted", "link": "/admin/content/sentence/"},
                ],
            },
            {
                "title": "Suggestions",
                "separator": False,
                "items": [
                    {"title": "All Suggestions", "icon": "link", "link": "/admin/suggestions/suggestion/"},
                    {"title": "Pipeline Runs", "icon": "play_circle", "link": "/admin/suggestions/pipelinerun/"},
                    {"title": "Diagnostics", "icon": "bug_report", "link": "/admin/suggestions/pipelinediagnostic/"},
                ],
            },
            {
                "title": "Analytics",
                "separator": False,
                "items": [
                    {"title": "Search Metrics", "icon": "search", "link": "/admin/analytics/searchmetric/"},
                    {"title": "Impact Reports", "icon": "trending_up", "link": "/admin/analytics/impactreport/"},
                ],
            },
            {
                "title": "Links & Graph",
                "separator": False,
                "items": [
                    {"title": "Broken Links", "icon": "link_off", "link": "/admin/graph/brokenlink/"},
                    {"title": "Existing Links", "icon": "hub", "link": "/admin/graph/existinglink/"},
                ],
            },
            {
                "title": "Audit",
                "separator": False,
                "items": [
                    {"title": "Audit Trail", "icon": "history", "link": "/admin/audit/auditentry/"},
                    {"title": "Reviewer Scorecards", "icon": "scorecard", "link": "/admin/audit/reviewerscorecard/"},
                    {"title": "Error Log", "icon": "error_outline", "link": "/admin/audit/errorlog/"},
                ],
            },
            {
                "title": "Plugins",
                "separator": False,
                "items": [
                    {"title": "Installed Plugins", "icon": "extension", "link": "/admin/plugins/plugin/"},
                ],
            },
            {
                "title": "Configuration",
                "separator": True,
                "items": [
                    {"title": "App Settings", "icon": "settings", "link": "/admin/core/appsetting/"},
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
}


# ── CORS ─────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:4200", "http://127.0.0.1:4200"],
)
CORS_ALLOW_CREDENTIALS = True


# ── Password Validation ───────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
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


# ── WordPress API (read-only, optional) ──────────────────────────

WORDPRESS_BASE_URL = env("WORDPRESS_BASE_URL", default="")
WORDPRESS_USERNAME = env("WORDPRESS_USERNAME", default="")
WORDPRESS_APP_PASSWORD = env("WORDPRESS_APP_PASSWORD", default="")


# ── ML / AI Settings ─────────────────────────────────────────────

ML_PERFORMANCE_MODE = env("ML_PERFORMANCE_MODE", default="BALANCED")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="BAAI/bge-small-en-v1.5")
EMBEDDING_BATCH_SIZE = env.int("EMBEDDING_BATCH_SIZE", default=32)
SPACY_MODEL = env("SPACY_MODEL", default="en_core_web_sm")

# Pipeline guardrails (non-negotiable product rules)
MAX_LINKS_PER_HOST_THREAD = 3
HOST_SCAN_WORD_LIMIT = 600


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
