"""
Test settings for XF Internal Linker V2.

These settings keep the runtime local and self-contained so the Django test
suite can run without Docker, PostgreSQL, or Redis.
"""

from .base import *  # noqa: F401, F403

DEBUG = False

SECRET_KEY = locals().get("SECRET_KEY", "test-secret-key")

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test.sqlite3",  # noqa: F405
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "xf-internal-linker-v2-tests",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
HTTP_WORKER_ENABLED = False
USE_NATIVE_EXTENSIONS = False  # tests mock or skip C++ extensions

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMBEDDING_MODEL = "BAAI/bge-m3"

# Keep expected 4xx validation responses from cluttering test output while still
# surfacing actual server-side failures.
LOGGING = {
    **LOGGING,  # noqa: F405
    "loggers": {
        **LOGGING["loggers"],  # noqa: F405
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
