"""SimpleTestCase coverage for the pipeline-gate prerequisite in readiness.py.

The 2026 health-check rename replaced ``check_gpu_faiss_health`` with
``check_faiss_index_health`` inside ``_prereq_pipeline_gate``. This test mocks the
three health functions the gate imports from ``apps.health.services`` so the gate
runs with no database, no FAISS index, and no Celery broker, then pins the exact
``ready`` dict and the exact ``blocked`` dict.

Because the production code imports the health functions by name from
``apps.health.services``, patching that module proves the renamed symbol is the
one actually called: if the import target were wrong the patch would not take and
the real (DB/IO-touching) function would run, breaking the no-database contract.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.suggestions import readiness


def _result(status: str, name: str = "faiss", detail: str = "stale") -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        service_name=name,
        issue_description=detail,
    )


class PrereqPipelineGateTests(SimpleTestCase):
    def test_when_all_health_checks_pass_then_gate_is_ready(self) -> None:
        with (
            mock.patch(
                "apps.health.services.check_faiss_index_health",
                return_value=_result("healthy"),
            ),
            mock.patch(
                "apps.health.services.check_ml_models_health",
                return_value=_result("healthy"),
            ),
            mock.patch(
                "apps.health.services.check_celery_health",
                return_value=_result("healthy"),
            ),
        ):
            row = readiness._prereq_pipeline_gate()

        self.assertEqual(
            row,
            {
                "id": "pipeline_gate",
                "category": "pipeline",
                "name": "Pipeline gate",
                "status": "ready",
                "plain_english": (
                    "Pipeline can run — GPU, models, and Celery all healthy."
                ),
                "next_step": "",
                "progress": 1.0,
                "affects": [],
            },
        )

    def test_when_faiss_unhealthy_then_gate_is_blocked_with_affects(self) -> None:
        with (
            mock.patch(
                "apps.health.services.check_faiss_index_health",
                return_value=_result("stale"),
            ),
            mock.patch(
                "apps.health.services.check_ml_models_health",
                return_value=_result("healthy"),
            ),
            mock.patch(
                "apps.health.services.check_celery_health",
                return_value=_result("healthy"),
            ),
        ):
            row = readiness._prereq_pipeline_gate()

        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["progress"], 0.0)
        self.assertEqual(
            row["affects"], ["signals", "math", "meta", "embeddings"]
        )
        self.assertEqual(
            row["plain_english"], "Pipeline is blocked: faiss: stale"
        )

    def test_when_all_three_unhealthy_then_blockers_joined_and_capped_at_three(
        self,
    ) -> None:
        # All three checks fail with distinct labels so the exact join string
        # pins the ``" · "`` separator. The gate only collects three checks, so
        # this also confirms every failed check is listed (the ``[:3]`` cap is
        # the no-op identity for three items, and a smaller cap would drop one).
        with (
            mock.patch(
                "apps.health.services.check_faiss_index_health",
                return_value=_result("stale", name="faiss", detail="index old"),
            ),
            mock.patch(
                "apps.health.services.check_ml_models_health",
                return_value=_result("down", name="models", detail="not loaded"),
            ),
            mock.patch(
                "apps.health.services.check_celery_health",
                return_value=_result("down", name="celery", detail="no worker"),
            ),
        ):
            row = readiness._prereq_pipeline_gate()

        self.assertEqual(
            row["plain_english"],
            "Pipeline is blocked: faiss: index old · models: not loaded · "
            "celery: no worker",
        )
