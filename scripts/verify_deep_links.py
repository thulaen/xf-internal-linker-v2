#!/usr/bin/env python3
"""CI gate for the DEEP-LINKING-CATALOG.md PARAMOUNT rule.

Walks the Angular route tree (`app.routes.ts`) and the deep-link catalog
(`deep-link-catalog.ts`) and fails with a clear message if any non-trivial
route is missing from the catalog.

KISS v1 covers the route check. Future enhancements (each `MatTabGroup`
child + each `MatDialog.open()` call-site) are noted in the doc but not
yet enforced — adding them is a tighter version of the same regex walk.

Exit codes:
  0  — every concrete app route is registered in the catalog
  1  — at least one route is missing
  2  — input file parse error (e.g. catalog moved)

Usage:
  python scripts/verify_deep_links.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTES_PATH = REPO_ROOT / "frontend" / "src" / "app" / "app.routes.ts"
CATALOG_PATH = REPO_ROOT / "frontend" / "src" / "app" / "core" / "routing" / "deep-link-catalog.ts"

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress success message; still print failures",
    )
    args = parser.parse_args()

    app_routes = parse_routes(ROUTES_PATH)
    catalog_routes = parse_catalog_routes(CATALOG_PATH)
    needed = app_routes - ROUTES_EXEMPT_FROM_CATALOG
    missing = sorted(needed - catalog_routes)

    if missing:
        sys.stderr.write(
            "\nFAIL verify_deep_links: routes registered in app.routes.ts but missing\n"
            "from the deep-link catalog. Per CLAUDE.md PARAMOUNT — Deep-linking\n"
            "catalog rule, every route MUST have an entry.\n\n"
        )
        for route in missing:
            sys.stderr.write(f"  /{route}\n")
        sys.stderr.write(
            "\nFix: add a DeepLinkEntry for each missing route in\n"
            "frontend/src/app/core/routing/deep-link-catalog.ts. See the\n"
            "shape documented at the top of that file (key, label,\n"
            "subtitle, route, searchTerms).\n"
        )
        return 1

    if not args.quiet:
        sys.stdout.write(
            f"OK verify_deep_links: {len(catalog_routes)} catalog entries cover "
            f"{len(needed)} app routes.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
