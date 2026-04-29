"""Spec-document viewer endpoint (masterplan Group A.5).

Serves repo-internal Markdown specs from ``docs/specs/*.md`` as
sanitised HTML so the Settings page's "View spec" Material dialog
can render them inside the existing app shell — no external links,
no separate browser tab, no static-file rebuild loop.

Security model
--------------
- Slug must match ``^[a-z0-9-]+$`` — rejects path traversal, ``..``,
  forward / back slashes, and any case folding tricks.
- Resolved path must stay strictly inside ``<repo>/docs/specs/``.
  Caught via ``Path.resolve()`` + prefix check; symlinks pointing
  outside the repo are rejected.
- File must end with ``.md``. We append the suffix server-side; the
  caller never names it.
- Content is rendered via the standard ``markdown`` package with
  the ``fenced_code``, ``tables``, and ``toc`` extensions. No raw
  HTML is allowed in the source — ``safe_mode`` strips it. (The
  source files are operator-controlled but defence-in-depth still
  applies.)

Reuses
------
- ``HttpResponse`` for JSON delivery via ``django.http.JsonResponse``
  — same pattern as every other ``apps.core.views`` endpoint.
- The repo-level path is derived from
  ``settings.BASE_DIR.parent / "docs" / "specs"``. ``BASE_DIR`` is
  the ``backend/`` dir per ``backend/config/settings/base.py:15``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import markdown as _markdown
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

#: Repo-internal docs/specs directory. Resolved once at import time
#: so each request just compares against a precomputed prefix.
SPECS_DIR: Path = (Path(settings.BASE_DIR).parent / "docs" / "specs").resolve()

#: Slug allow-list. Reject anything that isn't lowercase alphanumeric
#: or hyphen — no dots, slashes, percent-encoded bytes, or unicode.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")

#: Markdown extensions enabled for spec rendering. Conservative set:
#: fenced code blocks, GitHub-style tables, and the table-of-contents
#: anchor generator. ``safe_mode`` is honored separately via the
#: ``markdown.markdown(..., output_format="html5")`` call.
_MARKDOWN_EXTENSIONS = ("fenced_code", "tables", "toc", "sane_lists")


def _safe_resolve(slug: str) -> Path | None:
    """Return the absolute path inside ``SPECS_DIR`` for *slug*, or None.

    Returns None for any slug that fails the allow-list, escapes the
    base directory via ``..`` or symlink, or doesn't resolve to an
    existing readable ``.md`` file. Never raises.
    """
    if not _SLUG_RE.match(slug):
        return None
    candidate = (SPECS_DIR / f"{slug}.md").resolve()
    try:
        candidate.relative_to(SPECS_DIR)
    except ValueError:
        # Symlink or `..` traversal pointed outside the specs dir.
        return None
    if not candidate.is_file():
        return None
    return candidate


def _extract_title(raw: str) -> str:
    """Pull the first ``# Heading`` line off the raw markdown for the dialog title.

    Falls back to the slug if the file has no top-level heading. Keeps
    the title work on the server so the frontend just binds it.
    """
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


@require_GET
def view_spec_markdown(request, slug: str):
    """Read ``docs/specs/<slug>.md``, render to HTML, return JSON.

    Response shape::

        {
            "slug":  "fr099-dangling-authority-redistribution-bonus",
            "title": "FR-099 — Dangling Authority Redistribution Bonus",
            "html":  "<h1>...</h1>...",
            "raw":   "# FR-099 — ...\\n..."
        }

    404 with ``{"detail": "..."}`` for unknown / forbidden slugs.
    """
    path = _safe_resolve(slug)
    if path is None:
        return JsonResponse(
            {"detail": f"Spec '{slug}' not found."},
            status=404,
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("view_spec_markdown: failed to read %s: %s", path, exc)
        return JsonResponse(
            {"detail": "Spec file is unreadable."},
            status=500,
        )

    html = _markdown.markdown(
        raw,
        extensions=list(_MARKDOWN_EXTENSIONS),
        output_format="html5",
    )
    title = _extract_title(raw) or slug

    return JsonResponse(
        {
            "slug": slug,
            "title": title,
            "html": html,
            "raw": raw,
        }
    )
