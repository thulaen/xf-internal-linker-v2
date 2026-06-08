#!/usr/bin/env python3
"""Idempotently prepend a SUPERSEDED banner to legacy plan Markdown files.

The project is now Python + Rust only. Several plan folders on the user's
Desktop (and one folder of saved Claude plans) describe a multi-language world
(Go / Haskell / C++ / Lua / Java) that is no longer the target. Those plans are
still useful for *ideas*, but agents must not implement their language choices —
``.githooks/check-removed-languages.py`` hard-blocks such commits.

This script stamps a one-line HTML-comment banner at the very top of every
``.md`` file in those folders so any reader (human or agent) sees the warning
first. It is idempotent: a file that already carries the marker is left exactly
as-is, so re-running the script is safe.

Pure core (unit-tested in ``scripts/test_banner_superseded_plans.py``):

  - ``banner_text()``  -> the exact one-line banner string.
  - ``needs_banner()`` -> False when the marker is already present.
  - ``apply_banner()`` -> banner + blank line prepended at the top, once.

The ``main()`` walker is intentionally NOT covered by the pure unit tests
because it touches absolute Desktop paths; it is a thin loop over the pure core.

Run the core tests::

    docker compose run --rm -T backend-quality \\
        bash -lc "cd /repo && python -m pytest scripts/test_banner_superseded_plans.py -q"

Apply the banners (host Python, real paths)::

    python scripts/banner_superseded_plans.py
"""

from __future__ import annotations

from pathlib import Path

# The stable substring used for idempotency. If this appears anywhere in a
# document, the file is treated as already bannered. Keep it in sync with
# ``banner_text()`` below.
MARKER = "⛔ SUPERSEDED — Python + Rust ONLY"

_BANNER = (
    "<!-- ⛔ SUPERSEDED — Python + Rust ONLY. Do NOT implement "
    "Go / Haskell / C++ / Lua / Java from this plan; such commits are "
    "hard-blocked by .githooks/check-removed-languages.py. Harvest IDEAS "
    "only. See docs/adr/0007-python-rust-two-language.md and "
    "docs/PYTHON-RUST-MIGRATION-PLAN.md. -->"
)

# Folders whose every ``.md`` file gets the banner. Recursive walk.
PLAN_FOLDERS = (
    Path("C:/Users/goldm/OneDrive/Desktop/Fallbacks Rewrite"),
    Path("C:/Users/goldm/OneDrive/Desktop/XF V2 Vault"),
    Path("C:/Users/goldm/OneDrive/Desktop/Testing framework"),
    Path("C:/Users/goldm/OneDrive/Desktop/K8S"),
    Path("C:/Users/goldm/OneDrive/Desktop/CloudBuild Mega Plan"),
    Path("C:/Users/goldm/.claude/plans"),
)

# The single CURRENT active plan in ~/.claude/plans — never banner it.
ACTIVE_PLAN_NAME = "continue-in-c-users-goldm-dev-xf-interna-dazzling-seahorse.md"


def banner_text() -> str:
    """Return the exact one-line SUPERSEDED banner (no trailing newline)."""
    return _BANNER


def needs_banner(content: str) -> bool:
    """True when *content* does not already carry the SUPERSEDED marker."""
    return MARKER not in content


def apply_banner(content: str) -> str:
    """Prepend the banner + a blank line to *content* if it is not stamped.

    Idempotent: if the marker is already present the content is returned
    unchanged, so ``apply_banner(apply_banner(x)) == apply_banner(x)``.
    """
    if not needs_banner(content):
        return content
    return f"{banner_text()}\n\n{content}"


def _markdown_files(folder: Path):
    """Yield every ``.md`` file under *folder* (recursive), sorted, if it exists."""
    if not folder.is_dir():
        return
    yield from sorted(folder.rglob("*.md"))


def _stamp_file(path: Path) -> bool:
    """Stamp one file. Return True if it was newly bannered, False if skipped."""
    content = path.read_text(encoding="utf-8")
    if not needs_banner(content):
        return False
    path.write_text(apply_banner(content), encoding="utf-8", newline="")
    return True


def main() -> dict[str, int]:
    """Walk every plan folder and stamp each ``.md`` file. Return counts."""
    newly_bannered = 0
    already_bannered = 0
    active_skipped = 0

    for folder in PLAN_FOLDERS:
        if not folder.is_dir():
            print(f"[skip] folder not found: {folder}")
            continue
        for md_path in _markdown_files(folder):
            if md_path.name == ACTIVE_PLAN_NAME:
                active_skipped += 1
                print(f"[active-plan SKIP] {md_path}")
                continue
            if _stamp_file(md_path):
                newly_bannered += 1
                print(f"[bannered] {md_path}")
            else:
                already_bannered += 1
                print(f"[already]  {md_path}")

    counts = {
        "newly_bannered": newly_bannered,
        "already_bannered": already_bannered,
        "active_plan_skipped": active_skipped,
    }
    print(
        "\n=== SUMMARY ===\n"
        f"newly bannered:      {newly_bannered}\n"
        f"already bannered:    {already_bannered}\n"
        f"active plan skipped: {active_skipped}"
    )
    return counts


if __name__ == "__main__":
    main()
