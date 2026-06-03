"""Convention-named SimpleTestCase coverage for apps/core/helpers/resource_aware_retry.py.

This file provides literal pinning to kill mutants and coverage for small pure 
functions in resource_aware_retry.py. DB/Network connections are completely avoided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.helpers import resource_aware_retry


class ResourceAwareRetryConstantLiteralTests(SimpleTestCase):
    def test_defaults_exact(self) -> None:
        self.assertEqual(
            resource_aware_retry._DEFAULTS,
            {
                "oom_batch_shrink_ratio": 0.5,
                "thermal_wait_seconds": 300,
                "disk_pressure_defer_seconds": 3600,
                "transient_backoff_base_seconds": 30,
                "transient_backoff_max_seconds": 1800,
                "max_retries": 5,
            },
        )

    def test_failure_classifiers_exact(self) -> None:
        self.assertEqual(
            resource_aware_retry._FAILURE_CLASSIFIERS,
            {
                "MemoryError": "oom",
                "OutOfMemoryError": "oom",
                "ConnectionError": "transient",
                "TimeoutError": "transient",
                "RequestException": "transient",
                "OperationalError": "transient",
                "DiskPressureError": "disk_pressure",
                "ThermalThrottleError": "thermal",
            },
        )


class ClassifyFailureTests(SimpleTestCase):
    def test_classify_failure_generic_oom(self) -> None:
        class OutOfMemoryError(Exception):
            pass
        self.assertEqual(resource_aware_retry.classify_failure(OutOfMemoryError()), "oom")

    def test_classify_failure_disk_pressure(self) -> None:
        class DiskPressureError(Exception):
            pass
        self.assertEqual(resource_aware_retry.classify_failure(DiskPressureError()), "disk_pressure")

    def test_classify_failure_other(self) -> None:
        self.assertEqual(resource_aware_retry.classify_failure(ValueError()), "other")

    def test_classify_failure_heuristic_oom(self) -> None:
        self.assertEqual(resource_aware_retry.classify_failure(Exception("out of memory")), "oom")

    def test_classify_failure_heuristic_disk_pressure(self) -> None:
        self.assertEqual(resource_aware_retry.classify_failure(Exception("disk full")), "disk_pressure")
