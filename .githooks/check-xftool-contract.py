#!/usr/bin/env python3
"""check-xftool-contract — QUALITY gate for the xftool Rust CLI tooling.

When a commit touches the xftool crate (``rust/tools/``), every catalogued
subcommand must obey the contract in ``docs/specs/fr-rust-cli-tooling.md``:

  1. **No duplicate subcommands** — one tool, one place (KISS / DRY).
  2. **A complete catalog row** — ``command`` + ``category`` + ``summary`` all
     non-empty (the catalog is what ``xftool list`` prints; it must be honest).
  3. **Its group module exists and carries unit tests** —
     ``rust/tools/src/commands/<group>.rs`` exists and contains ``#[cfg(test)]``.
  4. **It is exercised by the end-to-end CLI test** — ``rust/tools/tests/cli.rs``
     invokes it (each word of the command appears as a quoted ``run(...)`` arg).

This gates the QUALITY of tooling changes, never their QUANTITY: it does NOT
force new tools and never blocks a commit for "too few" tools — it only blocks
a duplicate, undocumented, or untested one. (Deliberately the opposite of a
"≥N tools per commit" quota — see ADR 0008 / the spec discussion.)

Rule-F plain-English failure: WHAT fired, WHY, and how to UNBLOCK. Exit 0 allow,
exit 2 block. Fires only when ``rust/tools/`` is in the staged change.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TOOLS_PREFIX = "rust/tools/"
CATALOG = Path("rust/tools/src/catalog.rs")
CLI_TESTS = Path("rust/tools/tests/cli.rs")
COMMANDS_DIR = Path("rust/tools/src/commands")

_ENTRY_RE = re.compile(
    r'CatalogEntry\s*\{\s*'
    r'command:\s*"(?P<command>[^"]*)"\s*,\s*'
    r'category:\s*"(?P<category>[^"]*)"\s*,\s*'
    r'mutates:\s*(?P<mutates>true|false)\s*,\s*'
    r'summary:\s*"(?P<summary>[^"]*)"\s*,?\s*'
    r'\}',
    re.DOTALL,
)


def staged_paths() -> list[str]:
    """Repo-relative paths added/copied/modified in the staged change."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def parse_catalog(text: str) -> list[dict[str, str]]:
    """Parse the CATALOG rows from catalog.rs source text."""
    return [m.groupdict() for m in _ENTRY_RE.finditer(text)]


def command_module_tests(commands_dir_files: dict[str, str]) -> dict[str, bool]:
    """Map group name -> whether its commands/<group>.rs has #[cfg(test)].

    ``commands_dir_files`` is {filename_stem: file_text} for every *.rs under
    commands/ except ``mod``.
    """
    return {stem: ("#[cfg(test)]" in text) for stem, text in commands_dir_files.items()}


def contract_violations(
    catalog_text: str,
    cli_tests_text: str,
    module_has_tests: dict[str, bool],
) -> list[str]:
    """Return a plain-English problem per contract violation (empty == clean)."""
    entries = parse_catalog(catalog_text)
    if not entries:
        return ["rust/tools/src/catalog.rs has no parseable CatalogEntry rows"]
    problems: list[str] = []
    seen: set[str] = set()
    for e in entries:
        cmd = e["command"].strip()
        if cmd in seen:
            problems.append(f"duplicate subcommand {cmd!r} in the catalog — one tool, one place (KISS/DRY)")
        seen.add(cmd)
        if not cmd or not e["category"].strip() or not e["summary"].strip():
            problems.append(f"incomplete catalog row for {cmd!r}: command/category/summary must all be non-empty")
        words = cmd.split()
        if not words:
            continue
        group = words[0]
        if group not in module_has_tests:
            problems.append(f"{cmd!r}: no command module rust/tools/src/commands/{group}.rs")
        elif not module_has_tests[group]:
            problems.append(f"{cmd!r}: module commands/{group}.rs has no #[cfg(test)] unit tests")
        for word in words:
            if f'"{word}"' not in cli_tests_text:
                problems.append(
                    f"{cmd!r}: not exercised by the e2e test - rust/tools/tests/cli.rs has no run(...) using \"{word}\""
                )
    return problems


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def main() -> int:
    if not any(p.startswith(TOOLS_PREFIX) for p in staged_paths()):
        return 0  # xftool not touched — nothing to check.

    catalog_text = _read(CATALOG)
    cli_text = _read(CLI_TESTS)
    if catalog_text is None or cli_text is None:
        sys.stderr.write(
            "FAIL check-xftool-contract: the xftool crate is incomplete.\n"
            "WHY: rust/tools/ is staged but its catalog and/or e2e tests are missing "
            f"(need {CATALOG} and {CLI_TESTS}).\n"
            "UNBLOCK: ship the catalog row and the tests/cli.rs case with the subcommand.\n"
        )
        return 2

    module_files: dict[str, str] = {}
    if COMMANDS_DIR.is_dir():
        for rs in COMMANDS_DIR.glob("*.rs"):
            if rs.stem == "mod":
                continue
            text = _read(rs)
            if text is not None:
                module_files[rs.stem] = text

    problems = contract_violations(catalog_text, cli_text, command_module_tests(module_files))
    if not problems:
        print(f"[XFTOOL CONTRACT: {len(parse_catalog(catalog_text))} subcommand(s): catalogued, deduped, tested]")
        return 0

    sys.stderr.write("FAIL check-xftool-contract: an xftool subcommand breaks the tooling contract.\n")
    sys.stderr.write(
        "WHY: every catalogued tool must be unique, have a complete catalog row, carry unit tests "
        "in its module, and be exercised by tests/cli.rs (docs/specs/fr-rust-cli-tooling.md). "
        "This gate checks QUALITY, never tool count.\n"
    )
    for problem in problems:
        sys.stderr.write(f"  - {problem}\n")
    sys.stderr.write(
        "UNBLOCK: fix each item above — dedupe, fill the catalog row, add the #[cfg(test)] unit "
        "tests + the tests/cli.rs case — then re-stage rust/tools/ and recommit.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
