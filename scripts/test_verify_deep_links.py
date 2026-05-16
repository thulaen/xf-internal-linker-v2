"""Tests for scoped deep-link verification."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_deep_links


def test_non_frontend_scope_skips_deep_link_checks() -> None:
    """Unrelated commits do not scan frontend routes, tabs, or dialogs."""

    paths = ["services/streamd/go.mod", "scripts/quality_debt_score.py"]

    assert verify_deep_links.should_skip_for_scope(paths) is True


def test_route_scope_runs_when_routes_or_catalog_change() -> None:
    """Route and catalog edits still run the strict deep-link check."""

    assert verify_deep_links.needs_route_check(["frontend/src/app/app.routes.ts"]) is True
    assert (
        verify_deep_links.needs_route_check(
            ["frontend/src/app/core/routing/deep-link-catalog.ts"]
        )
        is True
    )


def test_warning_scan_uses_changed_frontend_templates_only() -> None:
    """Tab and dialog warning scans are limited to changed frontend files."""

    paths = [
        "frontend/src/app/demo/demo.component.html",
        "frontend/src/app/demo/demo.component.ts",
        "frontend/src/app/demo/demo.component.spec.ts",
        "backend/apps/demo/views.py",
    ]

    assert verify_deep_links.warning_scope_paths(paths) == [
        "frontend/src/app/demo/demo.component.html",
        "frontend/src/app/demo/demo.component.ts",
    ]
