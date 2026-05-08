"""
Celery application configuration for XF Internal Linker V2.

All background ML jobs (import, embed, pipeline, ranking) run as Celery tasks.
Heavy processing NEVER happens inline in request handlers.
"""

import os

from celery import Celery

# Django settings module for Celery workers
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("xf_linker")

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
    print(f"Request: {self.request!r}")


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
    """Reset every Django DB connection in each forked worker process.

    Celery's prefork pool spawns workers via ``os.fork()``. Without this
    hook, every forked child inherits the parent process's psycopg 3
    connection pool — sharing TCP sockets to Postgres. When two
    children execute at the same time on the inherited connection, the
    Postgres wire protocol gets interleaved and the first symptom is
    ``OperationalError: sending query failed: another command is
    already in progress`` followed by a cascade of
    ``InternalError: current transaction is aborted`` errors that
    bork every task on the affected pool slot.

    Closing connections here forces psycopg to open fresh per-process
    connections on first use, isolating each fork. This is the
    Django/Celery canonical fix — see Django ticket #14241 and the
    psycopg 3 docs §4.5 "Connection pools and forking".
    """
    from django.db import connections

    for conn in connections.all():
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — best-effort; a failed close should not stop fork.
            pass
