"""In-process registry of job entrypoints.

Each callable that the runner can invoke is registered here via the
``@scheduled_job`` decorator. The registry is populated at import time —
the runner looks up ``JOB_REGISTRY[job.key]`` to find the Python
function for a ScheduledJob.

Checkpoint contract
-------------------

Every registered entrypoint accepts exactly two arguments::

    def entrypoint(job: ScheduledJob, checkpoint: Checkpoint) -> None:
        for step in ...:
            do_work(step)
            checkpoint(progress_pct=50.0, message="Halfway through step 3")

``checkpoint`` is a callable provided by the runner. It does three
things on every call:

1. Persists progress to ``ScheduledJob.progress_pct`` and
   ``current_message``.
2. Broadcasts a progress frame to the Channels group (PR-B.4 wires this).
3. Checks ``ScheduledJob.pause_token`` — if True, raises
   ``PauseRequested`` which the runner catches and converts into a
   clean "paused" transition.

The checkpoint callable is only valid for the lifetime of one run;
holding a reference across runs is a bug.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import JOB_PRIORITY_MEDIUM

logger = logging.getLogger(__name__)


class PauseRequested(Exception):
    """Raised from inside a checkpoint when the job's pause_token flipped to True.

    The runner catches this, marks the job as paused, and releases the
    Redis lock so the next queued job can run. The paused job stays
    in the DB with its progress preserved; a later ``resume`` API
    call flips pause_token back off and the job picks up from its
    last checkpoint.
    """


class Checkpoint(Protocol):
    """What the runner hands each entrypoint."""

    def __call__(self, *, progress_pct: float, message: str = "") -> None: ...


#: Entrypoint signature. Kept explicit so type checkers catch registry
#: drift. The entrypoint returns None on success; raising any exception
#: (other than PauseRequested) transitions the job to `failed`.
Entrypoint = Callable[[object, Checkpoint], None]


@dataclass(frozen=True)
class JobDefinition:
    """Metadata for one registered job."""

    key: str
    display_name: str
    priority: str
    cadence_seconds: int
    estimate_seconds: int
    entrypoint: Entrypoint


#: The in-process registry. Populated at import time by ``@scheduled_job``
#: decorators. Don't mutate directly — use ``scheduled_job()`` to add
#: entries and ``unregister_for_test()`` inside tests.
JOB_REGISTRY: dict[str, JobDefinition] = {}


def scheduled_job(
    key: str,
    *,
    display_name: str,
    cadence_seconds: int,
    estimate_seconds: int,
    priority: str = JOB_PRIORITY_MEDIUM,
):
    """Register an entrypoint against a stable key.

    Usage::

        from apps.scheduled_updates.registry import scheduled_job

        @scheduled_job(
            "pagerank_refresh",
            display_name="PageRank refresh",
            cadence_seconds=86400,
            estimate_seconds=300,
            priority=JOB_PRIORITY_HIGH,
        )
        def run_pagerank_refresh(job, checkpoint):
            ...

    Re-registering the same key raises a loud error — two entrypoints
    per key would silently drop whichever ran second at import time.
    """

    def decorator(fn: Entrypoint) -> Entrypoint:
        if key in JOB_REGISTRY:
            raise RuntimeError(
                f"scheduled_job('{key}') is already registered — "
                f"two entrypoints for the same key would shadow each other. "
                f"Existing handler: {JOB_REGISTRY[key].entrypoint!r}"
            )
        JOB_REGISTRY[key] = JobDefinition(
            key=key,
            display_name=display_name,
            priority=priority,
            cadence_seconds=cadence_seconds,
            estimate_seconds=estimate_seconds,
            entrypoint=fn,
        )
        logger.debug(
            "scheduled_job registered key=%s priority=%s estimate=%ss",
            key,
            priority,
            estimate_seconds,
        )
        return fn

    return decorator


def unregister_for_test(key: str) -> None:
    """Drop an entry from the registry. Only call from tests."""
    JOB_REGISTRY.pop(key, None)


def lookup(key: str) -> JobDefinition | None:
    """Return the JobDefinition for *key*, or None when unknown."""
    return JOB_REGISTRY.get(key)
