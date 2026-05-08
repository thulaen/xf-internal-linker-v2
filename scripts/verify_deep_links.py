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


def find_template_tab_labels(root: Path) -> list[tuple[str, int, str]]:
    """Return [(file, line_no, label), ...] for every literal mat-tab label."""
    out: list[tuple[str, int, str]] = []
    for html in root.rglob("*.html"):
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


def find_dialog_open_calls(root: Path) -> list[tuple[str, int, str]]:
    """Return [(file, line_no, component_name), ...] for dialog.open() sites."""
    out: list[tuple[str, int, str]] = []
    for ts in root.rglob("*.ts"):
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


def main() -> int:
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
    args = parser.parse_args()

    app_routes = parse_routes(ROUTES_PATH)
    catalog_routes = parse_catalog_routes(CATALOG_PATH)
    needed = app_routes - ROUTES_EXEMPT_FROM_CATALOG
    missing_routes = sorted(needed - catalog_routes)

    # Strict scope: missing routes fail the gate.
    if missing_routes:
        sys.stderr.write(
            "\nFAIL verify_deep_links: routes registered in app.routes.ts but missing\n"
            "from the deep-link catalog. Per CLAUDE.md PARAMOUNT — Deep-linking\n"
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
        return 1

    # Informational scope: tab + dialog gaps are reported but don't fail.
    warnings_emitted = 0
    if not args.no_warn:
        warnings_emitted = _emit_tab_and_dialog_warnings()

    if not args.quiet:
        sys.stdout.write(
            f"OK verify_deep_links: {len(catalog_routes)} catalog entries cover "
            f"{len(needed)} app routes."
        )
        if warnings_emitted:
            sys.stdout.write(
                f"  ({warnings_emitted} informational tab/dialog gap"
                f"{'s' if warnings_emitted != 1 else ''} reported above; "
                "does not fail the gate.)"
            )
        sys.stdout.write("\n")
    return 0


def _emit_tab_and_dialog_warnings() -> int:
    """Print warnings for unregistered MatTabGroup labels + MatDialog.open call-sites.

    Returns the number of unique gaps reported.
    """
    catalog_tabs = parse_catalog_tabs(CATALOG_PATH)
    catalog_dialogs = parse_catalog_dialogs(CATALOG_PATH)
    tabs = find_template_tab_labels(TEMPLATES_ROOT)
    dialogs = find_dialog_open_calls(TS_ROOT)

    # Dedup by name so we report each gap once even if it appears in many places.
    missing_tabs: dict[str, tuple[str, int]] = {}
    for file, line_no, label in tabs:
        if label not in catalog_tabs and label not in missing_tabs:
            missing_tabs[label] = (file, line_no)

    missing_dialogs: dict[str, tuple[str, int]] = {}
    for file, line_no, component in dialogs:
        if component not in catalog_dialogs and component not in missing_dialogs:
            missing_dialogs[component] = (file, line_no)

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


if __name__ == "__main__":
    sys.exit(main())
