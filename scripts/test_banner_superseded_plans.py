"""Tests for the SUPERSEDED-banner prepender for legacy plan folders.

The pure core lives in ``scripts/banner_superseded_plans.py``:

  - ``banner_text()``    -> the exact one-line HTML comment banner.
  - ``needs_banner()``   -> False when the marker substring is already present.
  - ``apply_banner()``   -> banner + blank line prepended at the very top,
                            idempotently.

Run with the backend-quality container (matches every other scripts test)::

    docker compose run --rm -T backend-quality \\
        bash -lc "cd /repo && python -m pytest scripts/test_banner_superseded_plans.py -q"
"""

from __future__ import annotations

from scripts.banner_superseded_plans import (
    MARKER,
    apply_banner,
    banner_text,
    needs_banner,
)


def test_banner_text_is_the_exact_one_line_banner() -> None:
    """The banner is a single HTML comment line containing the marker."""
    banner = banner_text()
    assert banner == (
        "<!-- ⛔ SUPERSEDED — Python + Rust ONLY. Do NOT implement "
        "Go / Haskell / C++ / Lua / Java from this plan; such commits are "
        "hard-blocked by .githooks/check-removed-languages.py. Harvest IDEAS "
        "only. See docs/adr/0007-python-rust-two-language.md and "
        "docs/PYTHON-RUST-MIGRATION-PLAN.md. -->"
    )
    assert "\n" not in banner
    assert MARKER in banner


def test_needs_banner_true_for_fresh_content() -> None:
    """A document without the marker needs the banner."""
    assert needs_banner("# Some old plan\n\nbody text\n") is True


def test_needs_banner_false_when_marker_already_present() -> None:
    """The marker substring anywhere in the content means no banner is needed."""
    already = banner_text() + "\n\n# Some old plan\n"
    assert needs_banner(already) is False
    # Marker mid-document still counts (idempotency must not double-stamp).
    assert needs_banner("intro\n" + MARKER + "\nmore\n") is False


def test_apply_banner_prepends_banner_and_blank_line_at_the_top() -> None:
    """A fresh file gets the banner, then a blank line, then the original body."""
    original = "# Old Plan\n\nDo a thing.\n"
    result = apply_banner(original)
    lines = result.split("\n")
    assert lines[0] == banner_text()
    assert lines[1] == ""  # blank line separator
    assert result.endswith(original)
    assert result.startswith(banner_text() + "\n\n")


def test_apply_banner_is_idempotent() -> None:
    """Applying the banner twice equals applying it once."""
    original = "# Old Plan\n\nDetails here.\n"
    once = apply_banner(original)
    twice = apply_banner(once)
    assert twice == once


def test_apply_banner_leaves_already_bannered_content_unchanged() -> None:
    """Content that already carries the marker is returned byte-for-byte."""
    already = banner_text() + "\n\n# Already done\n"
    assert apply_banner(already) == already


def test_apply_banner_on_empty_file_still_stamps_once() -> None:
    """An empty document gets exactly one banner and is then idempotent."""
    stamped = apply_banner("")
    assert stamped.startswith(banner_text() + "\n\n")
    assert apply_banner(stamped) == stamped
