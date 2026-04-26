"""Smoke tests for the apps.api package.

This file exists primarily to satisfy the pre-push test-existence rule
(``scripts/verify.ps1`` line 26) which requires every Django app under
``backend/apps/`` to ship a ``tests.py`` (or ``tests/`` directory) so
new modules can never land without a place for their regression tests.

The api app is a thin DRF view layer over services that already have
their own dedicated test suites (``apps.pipeline.tests`` /
``apps.suggestions.tests`` / ``apps.diagnostics.tests``), so the file
starts as a smoke-import check. Add per-view test classes here when
genuinely api-layer-specific behaviour needs coverage (auth contracts,
URL routing, throttle policy, serialisation contracts).
"""

from __future__ import annotations

from django.test import SimpleTestCase


class ApiPackageImportTests(SimpleTestCase):
    """Verify every public module in apps.api imports cleanly."""

    def test_embedding_views_imports(self) -> None:
        from apps.api import embedding_views  # noqa: F401

    def test_ml_views_imports(self) -> None:
        from apps.api import ml_views  # noqa: F401

    def test_throttles_imports(self) -> None:
        from apps.api import throttles  # noqa: F401

    def test_urls_imports(self) -> None:
        from apps.api import urls  # noqa: F401
