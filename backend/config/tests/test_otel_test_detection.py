"""Tests for OpenTelemetry test-run detection in base settings."""

from __future__ import annotations

from django.test import SimpleTestCase
from opentelemetry.sdk.trace.export import SpanExportResult

from config.settings import base


class OpenTelemetryTestDetectionTests(SimpleTestCase):
    def test_pytest_run_is_classified_as_test_run(self) -> None:
        self.assertTrue(base._IS_TEST_RUN)


class GracefulTelemetryExporterTests(SimpleTestCase):
    def test_export_failure_returns_failure_without_raising(self) -> None:
        exporter = base._GracefulTelemetryExporter(
            _RaisingExporter(),
            failure_result=SpanExportResult.FAILURE,
        )

        result = exporter.export(["span"])

        self.assertEqual(result, SpanExportResult.FAILURE)

    def test_export_failure_accepts_metric_timeout_keyword(self) -> None:
        exporter = base._GracefulTelemetryExporter(
            _RaisingExporter(),
            failure_result=SpanExportResult.FAILURE,
        )

        result = exporter.export(["metric"], timeout_millis=100)

        self.assertEqual(result, SpanExportResult.FAILURE)

    def test_flush_failure_returns_false_without_raising(self) -> None:
        exporter = base._GracefulTelemetryExporter(
            _RaisingExporter(),
            failure_result=SpanExportResult.FAILURE,
        )

        self.assertFalse(exporter.force_flush(timeout_millis=100))

    def test_shutdown_failure_does_not_raise(self) -> None:
        exporter = base._GracefulTelemetryExporter(
            _RaisingExporter(),
            failure_result=SpanExportResult.FAILURE,
        )

        exporter.shutdown()

    def test_shutdown_failure_accepts_timeout_keyword(self) -> None:
        exporter = base._GracefulTelemetryExporter(
            _RaisingExporter(),
            failure_result=SpanExportResult.FAILURE,
        )

        exporter.shutdown(timeout=100)


class _RaisingExporter:
    def export(self, spans, **kwargs):
        raise TimeoutError("collector timed out")

    def force_flush(self, timeout_millis=30000):
        raise TimeoutError("collector timed out")

    def shutdown(self, **kwargs):
        raise TimeoutError("collector timed out")
