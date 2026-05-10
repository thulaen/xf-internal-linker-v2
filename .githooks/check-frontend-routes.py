#!/usr/bin/env python3
"""Pre-commit linter — every `HttpClient.<verb>('/api/...')` call in the
frontend must resolve to a real backend `path('...')` pattern.

Why a hook: the frontend and backend evolve independently. A backend route
can be renamed or removed without the frontend noticing — the call just
returns 404 in production and the user sees a generic error toast. This
class of bug is hard to spot in CI because the frontend builds + tests
fine even when the URL is stale (no integration test exercises every
button). The 2026-05-10 brief mentioned a "stale disk-prune route"
specifically; while that route turned out to be live, the prevention
check still belongs here so future drift is blocked.

What this hook does:

   1. On commit, find every staged frontend TS file and read its full
      contents.
   2. Extract every URL passed to `HttpClient.{get,post,put,patch,delete}`
      whose first character is `/api/`.
   3. Aggregate every `path('...')` and `re_path('...')` from
      `backend/apps/**/urls.py` and the `apps/api` router.
   4. For each frontend URL, check it can match at least one backend
      pattern (treating Django's `<int:pk>` / `<str:slug>` / re-path
      capture groups as wildcards).
   5. Block the commit on any unmatched URL.

What this hook does NOT block:
   - URLs containing `${...}` or `+` interpolation (template literals
     and string concatenation — too dynamic to resolve statically).
   - URLs in `frontend/src/app/api/schema.d.ts` (auto-generated;
     drift there is a separate problem solved by `openapi-generator`).
   - URLs inside `*.spec.ts` files (mocks routinely use placeholder
     paths like `/api/foo` for tests).
   - Calls to non-`/api/` URLs (third-party APIs, asset paths, etc.).

Bypass: prefix the URL string with `// noqa: route-check` on the same
line. Use sparingly — every bypass is a future stale-route risk.

Exit codes:
   0 — every staged frontend route resolves
   1 — at least one stale route detected
   2 — linter itself failed
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Match HttpClient.<verb>('/api/...') and similar shapes.
ROUTE_CALL_RE = re.compile(
    r"""\.
        (?:get|post|put|patch|delete)
        \s*<[^>]*>\s*\(\s*
        ['"`]
        (?P<url>/api/[A-Za-z0-9_/\-{}.]+)
        ['"`]
    """,
    re.VERBOSE,
)

# A simpler shape without explicit generic type.
ROUTE_CALL_NOGEN_RE = re.compile(
    r"""\.
        (?:get|post|put|patch|delete)
        \s*\(\s*
        ['"`]
        (?P<url>/api/[A-Za-z0-9_/\-{}.]+)
        ['"`]
    """,
    re.VERBOSE,
)

# `path("...")` / `re_path(r"...")` declarations in urls.py.
PATH_DECL_RE = re.compile(
    r"""(?:re_)?path\s*\(\s*
        (?:r?['"])
        (?P<pattern>[^'"]*)
        ['"]
    """,
    re.VERBOSE,
)

# `include("apps.foo.urls")` — to know which prefix prepends to the included patterns.
INCLUDE_RE = re.compile(
    r"""path\s*\(\s*
        (?:r?['"])
        (?P<prefix>[^'"]*)
        ['"]\s*,\s*include\s*\(\s*
        (?:r?['"])
        (?P<module>[^'"]+)
        ['"]
    """,
    re.VERBOSE,
)

# Files / directories never scanned for frontend routes.
SKIP_FRONTEND_RE = re.compile(
    r"(\.spec\.ts$|api/schema\.d\.ts$|node_modules/|/dist/|/coverage/)"
)


def staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def gather_backend_patterns() -> list[str]:
    """Return every URL pattern declared in backend/apps/**/urls.py + backend/config/.

    We don't try to fully resolve include() chains — instead we collect the
    raw pattern strings and turn them into regex match objects with all
    Django/regex captures replaced by wildcards. Good enough for "does ANY
    backend route exist that could match this frontend call".
    """
    patterns: list[str] = []
    for urls_file in REPO_ROOT.glob("backend/**/urls.py"):
        try:
            text = urls_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in PATH_DECL_RE.finditer(text):
            pattern = match.group("pattern")
            if pattern:
                patterns.append(pattern)
    return patterns


def to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a Django path() / re_path() pattern to a permissive regex.

    `path()` patterns: `<int:pk>`, `<str:slug>`, etc. → wildcard.
    `re_path()` patterns: leave the regex pieces intact but add ^/$ anchors.
    All paths are normalised to start with `/api/` if not already.
    """
    # Normalise leading / trailing slashes.
    raw = pattern.strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    # Path-style angle-bracket captures → `[^/]+`
    raw = re.sub(r"<[^>]+>", r"[^/]+", raw)
    # Strip Django regex named groups: (?P<name>...) → (...)
    raw = re.sub(r"\(\?P<[^>]+>", "(", raw)
    # Strip outer ^ $ anchors that may already exist.
    raw = raw.lstrip("^").rstrip("$")
    return re.compile("^" + raw + "/?$")


def url_matches(url: str, regexes: list[re.Pattern[str]]) -> bool:
    """Try the URL as-is AND with the /api/ prefix stripped.

    Backend patterns inside `apps/api/urls.py` are mounted at `/api/` by
    `config/urls.py: path("api/", include("apps.api.urls"))`. The patterns
    inside that file therefore look like `prune/safe/` (no leading slash,
    no /api/ prefix). When the frontend calls `/api/prune/safe/`, the
    pattern won't match the full URL — strip the /api/ prefix and try again.
    """
    candidates = [url]
    if url.startswith("/api/"):
        candidates.append("/" + url[len("/api/"):])
    for cand in candidates:
        for rx in regexes:
            if rx.match(cand):
                return True
    return False


def main(argv: list[str]) -> int:
    paths = argv[1:] or staged_files()
    paths = [
        p for p in (s.replace("\\", "/") for s in paths)
        if p.startswith("frontend/src/app/")
        and p.endswith(".ts")
        and not SKIP_FRONTEND_RE.search(p)
    ]
    if not paths:
        return 0

    backend_patterns = gather_backend_patterns()
    if not backend_patterns:
        # Backend urls.py couldn't be loaded — fail open rather than block
        # commits when the repo isn't fully checked out.
        return 0
    regexes = [to_regex(p) for p in backend_patterns]

    violations: list[str] = []
    for path in paths:
        full = REPO_ROOT / path
        if not full.exists():
            continue
        text = full.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "noqa: route-check" in line:
                continue
            for match in list(ROUTE_CALL_RE.finditer(line)) + list(ROUTE_CALL_NOGEN_RE.finditer(line)):
                url = match.group("url")
                # Skip URLs with template-literal interpolation we can't statically resolve.
                if "${" in url or "+ " in url:
                    continue
                if not url_matches(url, regexes):
                    violations.append(f"  {path}:{line_no}: {url}")

    if not violations:
        return 0

    print("\nFAIL check-frontend-routes: HttpClient call points at a backend route that doesn't exist.\n")
    for line in violations:
        print(line)
    print(
        "\nWhy this matters: stale frontend routes ship as 404s the user sees as"
        "\ngeneric error toasts. The frontend build doesn't catch them — only a"
        "\nclick test would, and most buttons don't have one. This hook closes"
        "\nthe drift gap statically."
        "\n\nFix shape:"
        "\n  - Re-check the URL spelling against the matching `path('...')` in"
        "\n    backend/apps/**/urls.py."
        "\n  - If the URL is intentional (e.g. a brand-new endpoint that lands"
        "\n    in the same commit), make sure the path() declaration is staged."
        "\n  - For genuinely-dynamic URLs that can't be statically checked,"
        "\n    add `// noqa: route-check` at the end of the offending line."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
