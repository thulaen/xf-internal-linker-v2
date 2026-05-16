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


def test_parse_route_and_catalog_files(tmp_path, monkeypatch) -> None:
    """Strict route parsing reads only the route and catalog source files."""

    routes = tmp_path / "app.routes.ts"
    catalog = tmp_path / "deep-link-catalog.ts"
    routes.write_text("path: 'dashboard'\npath: 'login'\n", encoding="utf-8")
    catalog.write_text("route: '/dashboard'\ntab: 'Overview'\ndialog: 'DemoDialog'\n", encoding="utf-8")
    monkeypatch.setattr(verify_deep_links, "ROUTES_PATH", routes)
    monkeypatch.setattr(verify_deep_links, "CATALOG_PATH", catalog)

    result = verify_deep_links.route_check_result(["frontend/src/app/app.routes.ts"])

    assert result["missing"] == []
    assert verify_deep_links.parse_catalog_tabs(catalog) == {"Overview"}
    assert verify_deep_links.parse_catalog_dialogs(catalog) == {"DemoDialog"}


def test_missing_route_prints_plain_failure(tmp_path, monkeypatch, capsys) -> None:
    """Missing routes still fail when route files are in scope."""

    routes = tmp_path / "app.routes.ts"
    catalog = tmp_path / "deep-link-catalog.ts"
    routes.write_text("path: 'dashboard'\n", encoding="utf-8")
    catalog.write_text("", encoding="utf-8")
    monkeypatch.setattr(verify_deep_links, "ROUTES_PATH", routes)
    monkeypatch.setattr(verify_deep_links, "CATALOG_PATH", catalog)

    status = verify_deep_links.main(["--paths", "frontend/src/app/app.routes.ts"])

    assert status == 1
    assert "/dashboard" in capsys.readouterr().err


def test_finds_tab_and_dialog_warnings(tmp_path, monkeypatch) -> None:
    """Warning scans read only the changed files passed to them."""

    root = tmp_path / "repo"
    html = root / "frontend/src/app/demo/demo.component.html"
    ts = root / "frontend/src/app/demo/demo.component.ts"
    html.parent.mkdir(parents=True)
    html.write_text('<mat-tab label="Missing"></mat-tab>\n', encoding="utf-8")
    ts.write_text("this.dialog.open(MissingDialog)\n", encoding="utf-8")
    catalog = root / "frontend/src/app/core/routing/deep-link-catalog.ts"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("tab: 'Known'\ndialog: 'KnownDialog'\n", encoding="utf-8")
    monkeypatch.setattr(verify_deep_links, "REPO_ROOT", root)
    monkeypatch.setattr(verify_deep_links, "CATALOG_PATH", catalog)

    warnings = verify_deep_links._emit_tab_and_dialog_warnings(
        [
            "frontend/src/app/demo/demo.component.html",
            "frontend/src/app/demo/demo.component.ts",
        ]
    )

    assert warnings == 2


def test_main_success_for_scoped_frontend_component(tmp_path, monkeypatch, capsys) -> None:
    """A component-only frontend edit can skip strict route checking."""

    catalog = tmp_path / "deep-link-catalog.ts"
    catalog.write_text("", encoding="utf-8")
    monkeypatch.setattr(verify_deep_links, "CATALOG_PATH", catalog)
    monkeypatch.setattr(verify_deep_links, "_emit_tab_and_dialog_warnings", lambda _paths=None: 0)

    status = verify_deep_links.main(["--paths", "frontend/src/app/demo/demo.component.ts"])

    assert status == 0
    assert "0 catalog entries cover 0 app routes" in capsys.readouterr().out
