#!/usr/bin/env python3
"""CI gate for the DEEP-LINKING-CATALOG.md PARAMOUNT rule.

Walks three scopes and compares each against the deep-link catalog
(`frontend/src/app/core/routing/deep-link-catalog.ts`):

  1. **Angular routes** (strict — exit 1 on miss).
     Pulls every `path:` literal from `app.routes.ts` and checks each
     non-trivial route is registered with a matching `route:` value.

  2. **MatTabGroup tabs** (informational — exit 0 even on miss).
     Walks every `*.html` template under `frontend/src/app/`, finds
     `<mat-tab label="...">` openings, and reports tabs whose label
     doesn't appear under any catalog entry's `tab` field. Reported as
     warnings so existing tabs aren't blocked from commits while the
     catalog is gradually backfilled.

  3. **MatDialog.open() call-sites** (informational — exit 0 even on
     miss). Walks every `*.ts` file, finds `dialog.open(<Component>...)`
     patterns, and reports dialog component names not present under any
     catalog entry's `dialog` field. Same warning-only behaviour as tabs.

Exit codes:
  0  — every concrete app route is registered (informational misses
       on tabs/dialogs do not fail the gate, but are listed in stderr)
  1  — at least one route is missing
  2  — input file parse error (e.g. catalog moved)

Usage:
  python scripts/verify_deep_links.py
  python scripts/verify_deep_links.py --quiet   # silence the success line
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTES_PATH = REPO_ROOT / "frontend" / "src" / "app" / "app.routes.ts"
CATALOG_PATH = REPO_ROOT / "frontend" / "src" / "app" / "core" / "routing" / "deep-link-catalog.ts"
TEMPLATES_ROOT = REPO_ROOT / "frontend" / "src" / "app"
TS_ROOT = REPO_ROOT / "frontend" / "src" / "app"

# Routes that genuinely don't need a catalog entry — they're not user-facing
# destinations the operator would deep-link to.
ROUTES_EXEMPT_FROM_CATALOG: frozenset[str] = frozenset(
    {
        "",                # empty path = redirect target
        "**",              # 404 / wildcard
        "login",           # auth-only screen, not a deep-link destination
        "server-error",    # error fallback page
        # Parametric/sub routes that are reached from a parent catalog entry
        # rather than directly typed; these are covered by their parent.
        "alerts/:id",
    }
)

# Regex: extract a single-quoted route value from a `path: 'foo'` line.
ROUTE_PATTERN = re.compile(r"path:\s*'([^']*)'")
# Regex: extract a single-quoted route value from a catalog `route: '/foo'`.
CATALOG_ROUTE_PATTERN = re.compile(r"route:\s*'([^']*)'")
# Regex: extract `tab: 'key'` from catalog entries.
CATALOG_TAB_PATTERN = re.compile(r"tab:\s*'([^']*)'")
# Regex: extract `dialog: 'ComponentName'` from catalog entries.
CATALOG_DIALOG_PATTERN = re.compile(r"dialog:\s*'([^']*)'")
# Regex: pull `<mat-tab label="Foo">` literal labels (binding-form
# `[label]="expr"` is skipped — the label is computed at runtime).
MAT_TAB_LABEL_PATTERN = re.compile(r"<mat-tab\s+label=\"([^\"]+)\"")
# Regex: pull the first argument from a `dialog.open(SomeComponent`
# call. The first capture is the variable holding the dialog service
# (commonly `dialog`, `matDialog`, `dlg`); the second is the component
# name. Skips lines where the open() argument is computed dynamically
# (e.g. `dialog.open(getCmp())`) since those can't be matched textually.
DIALOG_OPEN_PATTERN = re.compile(r"\b(\w*[Dd]ialog)\.open\(\s*([A-Z]\w+)")

# Templates / TS files we don't scan (irrelevant to deep-link surface).
SKIP_FILE_PATTERNS = (
    re.compile(r"\.spec\.ts$"),
    re.compile(r"/(node_modules|dist|coverage)/"),
    re.compile(r"/generated/"),
)


def parse_routes(routes_path: Path) -> set[str]:
    """Pull every `path:` literal out of app.routes.ts."""
    if not routes_path.exists():
        sys.stderr.write(f"verify_deep_links: routes file not found: {routes_path}\n")
        sys.exit(2)
    text = routes_path.read_text(encoding="utf-8")
    return set(ROUTE_PATTERN.findall(text))


def parse_catalog_routes(catalog_path: Path) -> set[str]:
    """Pull every `route:` literal out of deep-link-catalog.ts.

    Catalog routes are stored with a leading slash (e.g. '/dashboard') while
    Angular `path:` values use the bare segment ('dashboard'). Strip the
    leading slash for an apples-to-apples comparison.
    """
    if not catalog_path.exists():
        sys.stderr.write(f"verify_deep_links: catalog file not found: {catalog_path}\n")
        sys.exit(2)
    text = catalog_path.read_text(encoding="utf-8")
    return {route.lstrip("/") for route in CATALOG_ROUTE_PATTERN.findall(text)}


def parse_catalog_tabs(catalog_path: Path) -> set[str]:
    """Every `tab:` literal in the catalog."""
    if not catalog_path.exists():
        return set()
    return set(CATALOG_TAB_PATTERN.findall(catalog_path.read_text(encoding="utf-8")))


def parse_catalog_dialogs(catalog_path: Path) -> set[str]:
    """Every `dialog:` literal in the catalog."""
    if not catalog_path.exists():
        return set()
    return set(CATALOG_DIALOG_PATTERN.findall(catalog_path.read_text(encoding="utf-8")))


def _should_skip(path: Path) -> bool:
    s = str(path).replace("\\", "/")
    return any(pat.search(s) for pat in SKIP_FILE_PATTERNS)


def find_template_tab_labels(root: Path, paths: list[str] | None = None) -> list[tuple[str, int, str]]:
    """Return [(file, line_no, label), ...] for every literal mat-tab label."""
    out: list[tuple[str, int, str]] = []
    for html in template_files(root, paths):
        if _should_skip(html):
            continue
        try:
            text = html.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in MAT_TAB_LABEL_PATTERN.findall(line):
                out.append((str(html.relative_to(REPO_ROOT)), line_no, match))
    return out


def find_dialog_open_calls(root: Path, paths: list[str] | None = None) -> list[tuple[str, int, str]]:
    """Return [(file, line_no, component_name), ...] for dialog.open() sites."""
    out: list[tuple[str, int, str]] = []
    for ts in script_files(root, paths):
        if _should_skip(ts):
            continue
        try:
            text = ts.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for _, component in DIALOG_OPEN_PATTERN.findall(line):
                out.append((str(ts.relative_to(REPO_ROOT)), line_no, component))
    return out


def template_files(root: Path, paths: list[str] | None) -> list[Path]:
    """Return template files for full or scoped warning scans."""
    if paths is None:
        return sorted(root.rglob("*.html"))
    return [REPO_ROOT / path for path in paths if path.endswith(".html")]


def script_files(root: Path, paths: list[str] | None) -> list[Path]:
    """Return script files for full or scoped warning scans."""
    if paths is None:
        return sorted(root.rglob("*.ts"))
    return [REPO_ROOT / path for path in paths if path.endswith(".ts")]


def scoped_paths(args: argparse.Namespace) -> list[str]:
    """Return paths supplied by commit tools."""
    paths = list(args.paths)
    if args.paths_env:
        paths.extend(os.environ.get(args.paths_env, "").splitlines())
    return [path.strip().replace("\\", "/") for path in paths if path.strip()]


def should_skip_for_scope(paths: list[str]) -> bool:
    """Return true when scoped paths cannot affect deep links."""
    return bool(paths) and not any(path.startswith("frontend/src/app/") for path in paths)


def needs_route_check(paths: list[str]) -> bool:
    """Return true when changed files can affect route catalog correctness."""
    route_files = {
        "frontend/src/app/app.routes.ts",
        "frontend/src/app/core/routing/deep-link-catalog.ts",
    }
    return not paths or any(path in route_files for path in paths)


def warning_scope_paths(paths: list[str]) -> list[str]:
    """Return changed frontend files used for tab and dialog warnings."""
    return [
        path
        for path in paths
        if path.startswith("frontend/src/app/")
        and path.endswith((".html", ".ts"))
        and not path.endswith(".spec.ts")
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = scoped_paths(args)

    if should_skip_for_scope(paths):
        if not args.quiet:
            sys.stdout.write("OK verify_deep_links: no changed frontend app files to check.\n")
        return 0

    route_result = route_check_result(paths)

    # Strict scope: missing routes fail the gate.
    if route_result["missing"]:
        write_missing_routes(route_result["missing"])
        return 1

    # Informational scope: tab + dialog gaps are reported but don't fail.
    warnings_emitted = 0
    if not args.no_warn:
        warnings_emitted = _emit_tab_and_dialog_warnings(warning_scope_paths(paths) or None)

    if not args.quiet:
        sys.stdout.write(
            f"OK verify_deep_links: {len(route_result['catalog'])} catalog entries cover "
            f"{len(route_result['needed'])} app routes."
        )
        if warnings_emitted:
            sys.stdout.write(
                f"  ({warnings_emitted} informational tab/dialog gap"
                f"{'s' if warnings_emitted != 1 else ''} reported above; "
                "does not fail the gate.)"
            )
        sys.stdout.write("\n")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress success message; still print warnings + failures",
    )
    parser.add_argument(
        "--no-warn",
        action="store_true",
        help="skip the informational tab + dialog warning scan",
    )
    parser.add_argument("--paths", nargs="*", default=[])
    parser.add_argument("--paths-env", default="")
    return parser.parse_args(argv)


def route_check_result(paths: list[str]) -> dict[str, set[str] | list[str]]:
    """Return route coverage data for strict deep-link checks."""
    if not needs_route_check(paths):
        return {"catalog": set(), "needed": set(), "missing": []}
    app_routes = parse_routes(ROUTES_PATH)
    catalog_routes = parse_catalog_routes(CATALOG_PATH)
    needed = app_routes - ROUTES_EXEMPT_FROM_CATALOG
    return {
        "catalog": catalog_routes,
        "needed": needed,
        "missing": sorted(needed - catalog_routes),
    }


def write_missing_routes(missing_routes: list[str]) -> None:
    """Print the strict route-catalog failure."""
    sys.stderr.write(
        "\nFAIL verify_deep_links: routes registered in app.routes.ts but missing\n"
        "from the deep-link catalog. Per CLAUDE.md PARAMOUNT - Deep-linking\n"
        "catalog rule, every route MUST have an entry.\n\n"
    )
    for route in missing_routes:
        sys.stderr.write(f"  /{route}\n")
    sys.stderr.write(
        "\nFix: add a DeepLinkEntry for each missing route in\n"
        "frontend/src/app/core/routing/deep-link-catalog.ts. See the\n"
        "shape documented at the top of that file (key, label,\n"
        "subtitle, route, searchTerms).\n"
    )


def _emit_tab_and_dialog_warnings(paths: list[str] | None = None) -> int:
    """Print warnings for unregistered MatTabGroup labels + MatDialog.open call-sites.

    Returns the number of unique gaps reported.
    """
    catalog_tabs = parse_catalog_tabs(CATALOG_PATH)
    catalog_dialogs = parse_catalog_dialogs(CATALOG_PATH)
    tabs = find_template_tab_labels(TEMPLATES_ROOT, paths)
    dialogs = find_dialog_open_calls(TS_ROOT, paths)

    # Dedup by name so we report each gap once even if it appears in many places.
    missing_tabs = missing_named_items(tabs, catalog_tabs)
    missing_dialogs = missing_named_items(dialogs, catalog_dialogs)

    if not missing_tabs and not missing_dialogs:
        return 0

    sys.stderr.write(
        "\nWARN verify_deep_links: tab and/or dialog gaps. Informational only —\n"
        "does NOT fail the gate. Backfill at your leisure by adding entries to\n"
        "the deep-link catalog with the matching `tab` or `dialog` field.\n\n"
    )
    if missing_tabs:
        sys.stderr.write(f"  Tabs without a catalog entry ({len(missing_tabs)}):\n")
        for label in sorted(missing_tabs):
            file, line_no = missing_tabs[label]
            sys.stderr.write(f"    {label!r:30s}  {file}:{line_no}\n")
    if missing_dialogs:
        sys.stderr.write(
            f"  Dialog components without a catalog entry ({len(missing_dialogs)}):\n"
        )
        for component in sorted(missing_dialogs):
            file, line_no = missing_dialogs[component]
            sys.stderr.write(f"    {component:30s}  {file}:{line_no}\n")
    sys.stderr.write("\n")
    return len(missing_tabs) + len(missing_dialogs)


def missing_named_items(
    found: list[tuple[str, int, str]],
    catalog_items: set[str],
) -> dict[str, tuple[str, int]]:
    """Return unique tab or dialog names missing from the catalog."""
    missing: dict[str, tuple[str, int]] = {}
    for file, line_no, name in found:
        if name not in catalog_items and name not in missing:
            missing[name] = (file, line_no)
    return missing


if __name__ == "__main__":
    sys.exit(main())
