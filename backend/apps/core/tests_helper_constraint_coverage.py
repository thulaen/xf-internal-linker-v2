"""CI gate: every Celery task in ``apps.*`` must carry ``@HelperConstraint``.

Plain English: the helper-PC router (Phase 4.9) reads each Celery task's
``@HelperConstraint`` decorator to decide whether to run the task on the
main PC or hand it off to a secondary "helper" machine. This test walks
every task that Celery has registered, filters to the ones defined in the
``apps.*`` module tree, and asserts each one carries the constraint
metadata. A new task added without the decorator fails CI here, so the
router can never silently fall back to ``None`` (= "no metadata, stay on
main forever").

Companion to the warning-only ``missing-helper-constraint`` rule in
``.githooks/check-forbidden-patterns.py``: the linter catches violations
at commit time, this test catches them at CI time. Belt + braces.
"""

from __future__ import annotations

import importlib
import pkgutil

from django.apps import apps as django_apps
from django.test import SimpleTestCase

# Minimum number of in-app tasks the Phase 4.9 router expects to see.
# Bumped only if a real reduction has happened (consolidation, removal).
# A drop below this threshold means the test's task-discovery walk
# silently skipped a tasks module — fail loud rather than skip silently.
_MIN_EXPECTED_APPS_TASKS = 60


def _import_every_apps_tasks_module() -> None:
    """Walk ``apps.*`` Django app configs and import every tasks module.

    Celery's ``app.autodiscover_tasks()`` is lazy — outside a worker, the
    tasks module of an app is not imported until something explicitly
    references it. This helper forces every ``apps.<app>.tasks*`` and
    ``apps.<app>.runner`` module to load so ``current_app.tasks`` is fully
    populated by the time the assertion below runs.
    """
    for app_config in django_apps.get_app_configs():
        if not app_config.name.startswith("apps."):
            continue
        package = importlib.import_module(app_config.name)
        package_path = getattr(package, "__path__", None)
        if package_path is None:
            continue
        for _finder, modname, _ispkg in pkgutil.iter_modules(package_path):
            if modname == "tasks" or modname.startswith("tasks_") or modname == "runner":
                try:
                    importlib.import_module(f"{app_config.name}.{modname}")
                except ImportError:
                    # Optional task modules (e.g. ones gated by a feature
                    # flag at import time) may not load cleanly outside a
                    # worker — they're outside this gate's scope.
                    continue


class HelperConstraintCoverageTests(SimpleTestCase):
    """Every registered Celery task in ``apps.*`` must have ``__helper_constraint__``."""

    def test_every_apps_task_has_helper_constraint(self) -> None:
        """No Celery task in ``apps.*`` may be missing ``@HelperConstraint``.

        The decorator stashes ``_ConstraintMeta`` on ``func.__helper_constraint__``;
        Celery's ``shared_task`` wrapper exposes the wrapped callable as
        ``task.run``. So we look for the metadata at ``task.run.__helper_constraint__``.
        """
        _import_every_apps_tasks_module()

        from celery import current_app

        in_app_tasks = {
            name: task
            for name, task in current_app.tasks.items()
            if (getattr(task, "__module__", "") or "").startswith("apps.")
        }

        # Guard against the silent-skip failure mode where the discovery
        # walk above misses every tasks module and the loop below trivially
        # passes against zero entries.
        self.assertGreaterEqual(
            len(in_app_tasks),
            _MIN_EXPECTED_APPS_TASKS,
            f"Expected at least {_MIN_EXPECTED_APPS_TASKS} apps.* Celery tasks "
            f"to be registered, found {len(in_app_tasks)}. The autodiscovery "
            "walk in this test probably missed a tasks module — investigate "
            "_import_every_apps_tasks_module before bumping the threshold.",
        )

        missing: list[str] = []
        for task_name, task in in_app_tasks.items():
            run = getattr(task, "run", None)
            module = getattr(task, "__module__", "") or ""
            if run is None:
                missing.append(f"{task_name} ({module}): task has no .run attribute")
                continue
            if getattr(run, "__helper_constraint__", None) is None:
                missing.append(f"{task_name} ({module})")

        if missing:
            joined = "\n  - ".join(missing)
            self.fail(
                "Celery tasks missing @HelperConstraint annotation:\n  - "
                f"{joined}\n\n"
                "Add the decorator just below @shared_task. See "
                "docs/HELPER-CONSTRAINT-RUBRIC.md for value guidance."
            )
