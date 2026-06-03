"""Helper-PC integration package (Phase 4.9).

This package wires the existing ``HelperNode`` model + ``helper_router``
routing engine into a small surface that NEW Celery tasks can use to
declare their helper-friendliness without touching the router internals.

Three exports:

    * ``HelperConstraint`` — class-style decorator that annotates a
      Celery task with the resource constraints it implies. Supports
      ``cpu_intensive=True / gpu_required=False / storage_writes_to=...
      / ram_peak_mb=N``. The annotation is read by ``route_task()`` to
      pick a helper or stay on the main coordinator.

    * ``HelperArchive`` — storage abstraction. Returns a ``Path`` the
      caller can write to. When a helper is connected the path lives on
      the helper's SMB / NFS / local share; otherwise it falls back to
      the project-relative ``media/helper_archive/`` so dev still works.

    * ``roster()`` — read-only summary of every connected helper +
      free disk + heartbeat age + active-jobs count. Powers the
      ``/api/helpers/`` endpoint and the Confidence Meter contributor.

Storage discipline: zero new tables. Reuses ``HelperNode`` (already in
``ARTIFACT_RULES`` via ``self_test_smoke``) and writes archive metadata
to single AppSetting rows.

Citations: pattern derived from Celery distributed routing docs +
``apps/core/helper_router.py:select_best_helper_node`` (Stage 8/10).
"""

from .constraint import HelperConstraint, get_constraint
from .archive import HelperArchive
from .roster import roster

__all__ = ["HelperConstraint", "HelperArchive", "roster", "get_constraint"]
