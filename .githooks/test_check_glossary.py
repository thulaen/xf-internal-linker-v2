"""Focused regression test for `check-glossary.py`'s ALLOWLIST.

The ALLOWLIST exempts certain ALL-CAPS English words from the
"new technical jargon" detector. Pre-commit chain infrastructure
terms (`HOOK`, `FINDING`, `BLOCKED`) appear in legitimate prose
across `scripts/precommit-docker.sh` and other infrastructure files
and must not trip the glossary check just because a diff shifts
their line numbers.

This test asserts the ALLOWLIST contains the three terms. Adding new
infrastructure jargon means adding a row to this test AND adding the
term to the ALLOWLIST in the same change.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


HOOK_PATH = Path(__file__).resolve().parent / "check-glossary.py"


def _load_allowlist() -> frozenset[str]:
    """Import check-glossary.py despite its hyphenated filename."""
    spec = importlib.util.spec_from_file_location("check_glossary", HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ALLOWLIST  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def allowlist() -> frozenset[str]:
    return _load_allowlist()


@pytest.mark.parametrize(
    "term",
    [
        "HOOK",
        "FINDING",
        "BLOCKED",
    ],
)
def test_precommit_chain_infrastructure_terms_in_allowlist(
    allowlist: frozenset[str], term: str
) -> None:
    """Each precommit-chain infrastructure noun must exempt the glossary check.

    `HOOK`, `FINDING`, `BLOCKED` appear in legitimate prose across
    `scripts/precommit-docker.sh` and similar files. A regression here
    means a future agent removed the terms from the ALLOWLIST and
    every commit that touches `scripts/precommit-docker.sh` will be
    bounced by `check-glossary` on a false positive.
    """
    assert term in allowlist, (
        f"{term!r} is missing from check-glossary.py's ALLOWLIST. "
        f"Without it, every edit to scripts/precommit-docker.sh or "
        f"similar infrastructure files that shifts lines containing "
        f"{term!r} would trip the 'new technical jargon' detector."
    )
