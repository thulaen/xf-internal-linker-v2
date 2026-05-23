# pylint: disable=undefined-variable,used-before-assignment
"""
Test settings for XF Internal Linker V2.

These settings keep the runtime local and self-contained by default. The
Docker-managed quality path sets XF_USE_POSTGRES_TEST_DB=1 so tests run
against PostgreSQL when Postgres-only fields or migrations are present.

The file-level ``# pylint: disable=undefined-variable,used-before-assignment``
directive on line 1 acknowledges that names like ``env``, ``BASE_DIR``,
``DATABASES``, and ``LOGGING`` are re-exported from
``config.settings.base`` via the ``from .base import *`` star-import.
PyLint cannot follow the star-import + ``__all__`` re-export idiom
statically, so the only correct shape is a documented file-level
disable; the runtime contract is pinned by
``backend/config/tests/test_settings_no_wildcard.py``.
"""

from .base import *  # noqa: F401, F403
# Wildcard import is safe here because base.py declares ``__all__`` at the
# bottom of the file. SonarSource's ``python:S2208`` documented exception
# clause does not raise when the source module declares ``__all__``.

DEBUG = False
TESTING = True

SECRET_KEY = locals().get("SECRET_KEY", "test-secret-key")

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

if env.bool("XF_USE_POSTGRES_TEST_DB", default=True):  # noqa: F405
    DATABASES["default"] = {  # noqa: F405
        **DATABASES["default"],  # noqa: F405
        "NAME": env("POSTGRES_TEST_DB", default="test_xf_linker"),  # noqa: F405
        "TEST": {"NAME": env("POSTGRES_TEST_DB", default="test_xf_linker")},  # noqa: F405
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 10},
    }
else:
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
