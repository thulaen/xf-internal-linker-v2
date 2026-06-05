"""Focused regression test for `check-glossary.py`'s ALLOWLIST.

The ALLOWLIST exempts certain ALL-CAPS English words from the
"new technical jargon" detector. Pre-commit chain infrastructure
terms (`HOOK`, `FINDING`, `BLOCKED`) appear in legitimate prose
across `scripts/precommit-docker.sh` and other infrastructure files
and must not trip the glossary check just because a diff shifts
their line numbers.

This test asserts the ALLOWLIST contains the known safe terms. Adding new
infrastructure jargon means adding a row to this test AND adding the
term to the ALLOWLIST in the same change.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


HOOK_PATH = Path(__file__).resolve().parent / "check-glossary.py"
KNOWN_SAFE_TERMS = (
    "HOOK",
    "FINDING",
    "BLOCKED",
    "XXXXXX",
    "SSH",
    "INJECTED",
    "RAISE",
    "WOULD",
    "PASSES",
    "UNLESS",
    "DIRECTLY",
    "ZERO",
    "ALWAYS-ON",
    "PGEXPORTER",
    "NCPU",
)


def _load_module():
    """Import check-glossary.py despite its hyphenated filename."""
    spec = importlib.util.spec_from_file_location("check_glossary", HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_allowlist() -> frozenset[str]:
    module = _load_module()
    return module.ALLOWLIST  # type: ignore[no-any-return]


class GlossaryAllowlistTests(unittest.TestCase):
    def test_known_safe_terms_in_allowlist(self) -> None:
        """Each known safe term must be exempt from the glossary check."""
        allowlist = _load_allowlist()

        for term in KNOWN_SAFE_TERMS:
            with self.subTest(term=term):
                self.assertIn(
                    term,
                    allowlist,
                    (
                        f"{term!r} is missing from check-glossary.py's ALLOWLIST. "
                        "Without it, edits that shift known safe words would trip "
                        "the 'new technical jargon' detector."
                    ),
                )

    def test_known_safe_terms_do_not_create_violations(self) -> None:
        module = _load_module()
        added_lines = [
            (
                "scripts/precommit-docker.sh",
                51,
                "HOOK FINDING BLOCKED XXXXXX SSH INJECTED RAISE WOULD PASSES "
                "UNLESS DIRECTLY ZERO ALWAYS-ON PGEXPORTER NCPU",
            )
        ]

        violations = module.find_violations(added_lines, glossary=set())

        self.assertEqual([], violations)

    def test_unknown_acronym_still_creates_violation(self) -> None:
        module = _load_module()
        added_lines = [("docs/example.md", 12, "A NEWJARGON value appears here")]

        violations = module.find_violations(added_lines, glossary=set())

        self.assertEqual([("NEWJARGON", "docs/example.md", 12)], violations)


if __name__ == "__main__":
    unittest.main()
