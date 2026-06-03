"""Convention tests for scripts/_rules_sync_helpers.py pure text helpers.

BDD:
  Given agent-rule markdown text and YAML-ish manifest lines
  When normalize_text / extract_section / replace_section / load helpers run
  Then line endings, section boundaries (next ABSOLUTE/PARAMOUNT heading), YAML
       value cleaning, and replacement output match exact strings — killing
       mutation survivors on the text-slicing logic.

Pure in-memory text — no filesystem reads (manifest loaded from a temp file).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rsh = _load("_rules_sync_helpers", "_rules_sync_helpers.py")


_DOC = (
    "intro line\n"
    "**ABSOLUTE — First rule** body of first.\n"
    "more of first.\n"
    "**PARAMOUNT — Second rule** body of second.\n"
)


class TestNormalizeText(TestCase):
    def test_crlf_to_lf_and_trailing_newline(self):
        self.assertEqual(rsh.normalize_text("a\r\nb  "), "a\nb\n")

    def test_already_clean_unchanged(self):
        self.assertEqual(rsh.normalize_text("a\nb"), "a\nb\n")


class TestExtractSection(TestCase):
    def test_extracts_to_next_shared_heading(self):
        out = rsh.extract_section(_DOC, "ABSOLUTE — First rule")
        self.assertEqual(out, "**ABSOLUTE — First rule** body of first.\nmore of first.\n")

    def test_last_section_runs_to_end(self):
        out = rsh.extract_section(_DOC, "PARAMOUNT — Second rule")
        self.assertEqual(out, "**PARAMOUNT — Second rule** body of second.\n")

    def test_missing_anchor_returns_empty(self):
        self.assertEqual(rsh.extract_section(_DOC, "ABSOLUTE — Nope"), "")


class TestReplaceSection(TestCase):
    def test_replaces_existing_section(self):
        out = rsh.replace_section(
            _DOC, "ABSOLUTE — First rule", "**ABSOLUTE — First rule** REPLACED.")
        self.assertIn("**ABSOLUTE — First rule** REPLACED.", out)
        self.assertNotIn("more of first.", out)
        self.assertIn("**PARAMOUNT — Second rule**", out)

    def test_appends_when_anchor_missing(self):
        out = rsh.replace_section(
            _DOC, "ABSOLUTE — Brand new", "**ABSOLUTE — Brand new** added.")
        self.assertIn("**ABSOLUTE — Brand new** added.", out)
        self.assertTrue(out.endswith("added.\n"))


class TestCleanYamlValue(TestCase):
    def test_strips_double_quotes(self):
        self.assertEqual(rsh._clean_yaml_value('"quoted"'), "quoted")

    def test_unquoted_passthrough(self):
        self.assertEqual(rsh._clean_yaml_value("  plain  "), "plain")


class TestLoadManifest(TestCase):
    def test_parses_keys_and_list_items(self):
        text = (
            "# comment\n"
            "agent_files:\n"
            '  - "AGENTS.md"\n'
            "  - CLAUDE.md\n"
            "shared_sections:\n"
            "  - Rule One\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8") as tf:
            tf.write(text)
            tmp = Path(tf.name)
        try:
            manifest = rsh.load_manifest(tmp)
        finally:
            tmp.unlink()
        self.assertEqual(manifest["agent_files"], ["AGENTS.md", "CLAUDE.md"])
        self.assertEqual(manifest["shared_sections"], ["Rule One"])


class TestIsSharedHeading(TestCase):
    def test_absolute_is_shared(self):
        self.assertTrue(rsh._is_shared_heading("**ABSOLUTE — x"))

    def test_paramount_is_shared(self):
        self.assertTrue(rsh._is_shared_heading("**PARAMOUNT — y"))

    def test_plain_line_not_shared(self):
        self.assertFalse(rsh._is_shared_heading("just text"))
