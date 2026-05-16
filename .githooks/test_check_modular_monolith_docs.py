"""Tests for slice 1 modular-monolith foundation documents.

Asserts the canonical architecture document, the 9 module stubs, the 5
Architecture Decision Records, the source-backed spec, the 14 new glossary
terms, and the strict per-agent rule are all in place. Slice 2 will turn this
test into a pre-commit hook; slice 1 keeps it as a focused regression test.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from unittest import TestCase


REPO_ROOT = Path(__file__).resolve().parent.parent

MODULAR_MONOLITH_DOC = REPO_ROOT / "docs" / "MODULAR-MONOLITH.md"
MODULE_DIR = REPO_ROOT / "docs" / "modules"
ADR_DIR = REPO_ROOT / "docs" / "adr"
SPEC_FILE = REPO_ROOT / "docs" / "specs" / "fr-modular-monolith.md"
PLAIN_ENGLISH_FILE = REPO_ROOT / "PLAIN-ENGLISH-RULE.md"
AGENTS_FILE = REPO_ROOT / "AGENTS.md"
CLAUDE_FILE = REPO_ROOT / "CLAUDE.md"
CODEX_FILE = REPO_ROOT / "CODEX.md"
GEMINI_FILE = REPO_ROOT / "GEMINI.md"
AI_CONTEXT_FILE = REPO_ROOT / "AI-CONTEXT.md"

MODULE_NAMES = (
    "platform",
    "content",
    "sources",
    "pipeline",
    "suggestions",
    "analytics",
    "graph",
    "operations",
    "governance",
    "services",
)

ADR_NUMBERS = (1, 2, 3, 4, 5, 6)

REQUIRED_DOC_PHRASES = (
    "module map",
    "public interface",
    "boundary rule",
    "dependency direction",
    "test plan",
    "stop condition",
)

REQUIRED_ADR_HEADINGS = ("Context", "Decision", "Consequences")

RULE_FILES = (AGENTS_FILE, CLAUDE_FILE, CODEX_FILE, GEMINI_FILE)

NEW_GLOSSARY_TERMS = (
    "modular monolith",
    "public interface",
    "boundary rule",
    "dependency direction",
    "ADR",
    "citation",
    "manifest",
    "shim",
    "deprecation",
    "golden test",
    "fitness function",
    "anti-corruption layer",
)

GLOSSARY_TERMS_REQUIRING_WORD_BOUNDARY = ("module",)

RULE_HEADER_RE = re.compile(
    r"^\*\*ABSOLUTE\s+[—-]\s+Modular Monolith", re.MULTILINE
)
SPEC_FRESHNESS_RE = re.compile(
    r"\[SPEC FRESHNESS:\s*reviewed_at=(\d{4}-\d{2}-\d{2})\s+"
    r"next_review=(\d{4}-\d{2}-\d{2})\]"
)
SPEC_CITED_RE = re.compile(
    r"\[SPEC CITED:\s*feature=([^\s]+)\s+kind=(\w+)\s+id=(\S+)\s+verified_at=([^\]]+)\]"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _current_year_month() -> str:
    today = _dt.date.today()
    return f"{today.year:04d}-{today.month:02d}"


class ModularMonolithFoundationTests(TestCase):
    """Slice 1 acceptance checks for the foundation documents."""

    def test_when_doc_present_then_h1_and_required_sections_exist(self) -> None:
        self.assertTrue(MODULAR_MONOLITH_DOC.exists(),
                        f"missing canonical doc: {MODULAR_MONOLITH_DOC}")
        text = _read(MODULAR_MONOLITH_DOC)
        self.assertRegex(text, re.compile(r"^#\s+Modular Monolith\b", re.MULTILINE),
                         "H1 must be '# Modular Monolith'")
        lowered = text.lower()
        for phrase in REQUIRED_DOC_PHRASES:
            self.assertIn(phrase, lowered,
                          f"MODULAR-MONOLITH.md missing required phrase: {phrase!r}")

    def test_when_module_dir_exists_then_all_listed_stubs_exist(self) -> None:
        self.assertTrue(MODULE_DIR.is_dir(),
                        f"missing module stub directory: {MODULE_DIR}")
        for name in MODULE_NAMES:
            stub = MODULE_DIR / f"{name}.md"
            self.assertTrue(stub.exists(), f"missing module stub: {stub}")
            body = _read(stub).lower()
            self.assertIn(name, body, f"stub {stub.name} must mention its module name")
            self.assertIn("public interface", body,
                          f"stub {stub.name} must mention 'public interface'")

    def test_when_adr_dir_exists_then_all_listed_adrs_have_nygard_sections(self) -> None:
        self.assertTrue(ADR_DIR.is_dir(),
                        f"missing ADR directory: {ADR_DIR}")
        for n in ADR_NUMBERS:
            prefix = f"{n:04d}-"
            matches = sorted(ADR_DIR.glob(f"{prefix}*.md"))
            self.assertEqual(
                len(matches), 1,
                f"expected exactly one ADR file starting with {prefix}, found {matches}",
            )
            body = _read(matches[0])
            for heading in REQUIRED_ADR_HEADINGS:
                self.assertRegex(
                    body,
                    re.compile(rf"^##\s+{heading}\b", re.MULTILINE),
                    f"ADR {matches[0].name} missing '## {heading}' section",
                )

    def test_when_spec_present_then_freshness_and_at_least_one_citation(self) -> None:
        self.assertTrue(SPEC_FILE.exists(), f"missing spec: {SPEC_FILE}")
        text = _read(SPEC_FILE)
        freshness = SPEC_FRESHNESS_RE.search(text)
        self.assertIsNotNone(freshness,
                             "spec must include [SPEC FRESHNESS: reviewed_at=... next_review=...]")
        reviewed_at = freshness.group(1)
        self.assertTrue(
            reviewed_at.startswith(_current_year_month()),
            f"spec [SPEC FRESHNESS] reviewed_at={reviewed_at} not in current month "
            f"{_current_year_month()}",
        )
        citations = SPEC_CITED_RE.findall(text)
        self.assertGreaterEqual(
            len(citations), 1,
            "spec must carry at least one [SPEC CITED: ...] line",
        )

    def test_when_plain_english_present_then_all_listed_new_terms_exist(self) -> None:
        text = _read(PLAIN_ENGLISH_FILE).lower()
        for term in NEW_GLOSSARY_TERMS:
            self.assertIn(
                term.lower(),
                text,
                f"PLAIN-ENGLISH-RULE.md missing new glossary term: {term!r}",
            )
        for term in GLOSSARY_TERMS_REQUIRING_WORD_BOUNDARY:
            pattern = re.compile(rf"\|\s*{re.escape(term)}\b", re.IGNORECASE)
            self.assertRegex(
                _read(PLAIN_ENGLISH_FILE),
                pattern,
                f"PLAIN-ENGLISH-RULE.md missing word-boundary glossary entry: {term!r}",
            )

    def test_when_rule_files_open_then_each_carries_absolute_modular_monolith(
        self,
    ) -> None:
        for path in RULE_FILES:
            text = _read(path)
            self.assertRegex(
                text,
                RULE_HEADER_RE,
                f"{path.name} missing '**ABSOLUTE — Modular Monolith' rule header",
            )
            self.assertIn(
                "docs/MODULAR-MONOLITH.md",
                text,
                f"{path.name} Modular Monolith rule must point at docs/MODULAR-MONOLITH.md",
            )

    def test_when_ai_context_open_then_session_gate_has_modular_monolith_subsection(
        self,
    ) -> None:
        text = _read(AI_CONTEXT_FILE)
        self.assertRegex(
            text,
            re.compile(r"^###\s+Modular Monolith\b", re.MULTILINE),
            "AI-CONTEXT.md Session Gate must contain a '### Modular Monolith' subsection",
        )
        self.assertIn(
            "docs/MODULAR-MONOLITH.md",
            text,
            "AI-CONTEXT.md Modular Monolith subsection must reference docs/MODULAR-MONOLITH.md",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
