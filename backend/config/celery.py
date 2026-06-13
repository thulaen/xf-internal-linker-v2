"""
Celery application configuration for XF Internal Linker V2.

All background ML jobs (import, embed, pipeline, ranking) run as Celery tasks.
Heavy processing NEVER happens inline in request handlers.
"""

import logging
import os

from celery import Celery

# Django settings module for Celery workers
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("xf_linker")
logger = logging.getLogger(__name__)

# Read config from Django settings, using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Named queues for routing different job types
app.conf.task_queues = {
    "default": {"exchange": "default", "routing_key": "default"},
    "pipeline": {"exchange": "pipeline", "routing_key": "pipeline"},
    "embeddings": {"exchange": "embeddings", "routing_key": "embeddings"},
}

app.conf.task_default_queue = "default"

# Expire task results after 1 hour so Redis does not grow without bound.
# Tasks that need longer retention should store results in the DB instead.
app.conf.result_expires = 3600


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    import logging as _logging

    _logging.getLogger(__name__).info("debug_task fired: request=%r", self.request)


# ── Startup catch-up ────────────────────────────────────────────────
# On worker boot, dispatch any overdue scheduled tasks that were missed
# while the laptop was off.  See docs/PERFORMANCE.md §5.

from celery.signals import worker_process_init, worker_ready  # noqa: E402


@worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):
    """Run startup catch-up when the Celery worker is fully initialised."""
    import django

    django.setup()
    from config.catchup import run_startup_catchup

    run_startup_catchup()


@worker_process_init.connect
def _close_db_connections_on_fork(**_kwargs):
    """Dispose every Django DB connection pool in each forked worker process.

    Celery's prefork pool spawns workers via ``os.fork()``. With psycopg 3's
    native connection pool (``DATABASES["default"]["OPTIONS"]["pool"]``),
    ``os.fork()`` duplicates the parent's live TCP sockets and the pool's
    background maintenance thread does not survive the fork. Calling
    ``conn.close()`` alone only RETURNS the current connection to the
    *inherited* pool — it leaves those duplicated sockets in place, so two
    forked children can be handed the same server connection and interleave
    on the wire. The first symptom is ``OperationalError: sending query
    failed`` / ``DatabaseError: lost synchronization with server``, followed
    by ``InvalidSavepointSpecification`` and ``InvalidCursorName`` as
    savepoints and server-side cursors created on one process's view of the
    socket vanish from another's.

    Disposing the pool (``close_pool``) drops the inherited pool entirely so
    psycopg builds a fresh per-process pool — new sockets, new background
    thread — on first use, isolating each fork. This is the Django/Celery
    canonical fix — see Django ticket #14241 and the psycopg 3 docs
    "Pool and forking".
    """
    from django.db import connections

    for conn in connections.all(initialized_only=True):
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — best-effort; a dead socket close must not stop fork.
            logger.debug("fork hook: connection close failed (ignored)", exc_info=True)
        close_pool = getattr(conn, "close_pool", None)
        if callable(close_pool):
            try:
                close_pool()
            except Exception:  # noqa: BLE001 — best-effort; a failed dispose must not stop fork.
                logger.debug("fork hook: pool dispose failed (ignored)", exc_info=True)
