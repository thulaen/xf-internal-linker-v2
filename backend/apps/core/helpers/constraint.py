"""``HelperConstraint`` decorator — declare a Celery task's resource needs.

Usage:

    from apps.core.helpers import HelperConstraint
    from celery import shared_task

    @shared_task(name="audience.country_alignment_refresh")
    @HelperConstraint(
        cpu_intensive=True,
        gpu_required=False,
        storage_writes_to="postgres_main",
        ram_peak_mb=512,
    )
    def country_alignment_refresh(...):
        ...

The annotation is stored on the wrapped function (``__helper_constraint__``)
so the routing engine + the operator-facing diagnostics can read it.
The decorator is order-sensitive — it must come INSIDE ``@shared_task``
so Celery's wrapper sees the annotated callable.

Storage-write targets:
    * ``postgres_main`` — writes go to the main PC's Postgres
      (only main-node tasks may write directly)
    * ``redis`` — writes go to Redis (any node)
    * ``helper_archive`` — writes go to the helper's SMB share
      (helper-node tasks; main reads later via SMB mount)
    * ``none`` — read-only / pure-compute task

Pre-commit hook (Phase 4.9 sub-gap 1) flags any new ``@shared_task`` with
no ``@HelperConstraint``. CI ``--strict`` mode blocks GPU code that
isn't routed via the ``gpu`` queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, TypeVar

F = TypeVar("F", bound=Callable[..., object])

StorageTarget = Literal["postgres_main", "redis", "helper_archive", "none"]


@dataclass(frozen=True, slots=True)
class _ConstraintMeta:
    """The data the routing engine reads off a decorated task."""

    cpu_intensive: bool
    gpu_required: bool
    storage_writes_to: StorageTarget
    ram_peak_mb: int
    # Optional ceiling used by retry-aware scheduling: if a task
    # historically takes longer than this, the router prefers to keep
    # it on the main node where Postgres latency is lower.
    expected_seconds_p50: int | None = None
    # Optional list of warmed-model keys the helper must already have
    # in cache (matches HelperNode.warmed_model_keys).
    requires_warmed_models: tuple[str, ...] = field(default_factory=tuple)


class HelperConstraint:
    """Class-style decorator: ``@HelperConstraint(cpu_intensive=True, ...)``.

    Plain-English: tells the system "this task is CPU-heavy, doesn't need
    a GPU, writes its results into Postgres on the main PC, and uses
    about 512 MB of RAM at peak." The router reads that metadata to pick
    which connected machine should run the task.
    """

    def __init__(
        self,
        *,
        cpu_intensive: bool = False,
        gpu_required: bool = False,
        storage_writes_to: StorageTarget = "postgres_main",
        ram_peak_mb: int = 256,
        expected_seconds_p50: int | None = None,
        requires_warmed_models: tuple[str, ...] = (),
    ) -> None:
        self.meta = _ConstraintMeta(
            cpu_intensive=cpu_intensive,
            gpu_required=gpu_required,
            storage_writes_to=storage_writes_to,
            ram_peak_mb=ram_peak_mb,
            expected_seconds_p50=expected_seconds_p50,
            requires_warmed_models=requires_warmed_models,
        )

    def __call__(self, func: F) -> F:
        # Stash the metadata on the function so the router (and the
        # /api/helpers/ endpoint) can introspect it later.
        func.__helper_constraint__ = self.meta  # type: ignore[attr-defined]
        return func


def get_constraint(callable_or_name: object) -> _ConstraintMeta | None:
    """Return the constraint metadata for a task, or None if undeclared.

    Accepts either the function object or a Celery task name string.
    Used by the routing engine + the diagnostics surface.
    """
    if callable(callable_or_name):
        return getattr(callable_or_name, "__helper_constraint__", None)
    if isinstance(callable_or_name, str):
        try:
            from celery import current_app

            task = current_app.tasks.get(callable_or_name)
            if task is None:
                return None
            return getattr(task.run, "__helper_constraint__", None)
        except Exception:  # noqa: forbidden-pattern silent-except — Celery import is optional at module load; missing-Celery callers should get None back, not an error.
            return None
    return None
