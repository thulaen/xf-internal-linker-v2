"""Tests for the pure Rust compiler warning parser (no DB, no network).

Covers Rust cargo/rustc/clippy arrow-location diagnostics plus edge cases.
Removed backend languages return no rows.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.services.compiler_warnings import (
    CompilerWarning,
    parse_warnings,
)


class RustParserTests(SimpleTestCase):
    def test_parses_multiline_clippy_block(self):
        block = (
            "warning: unused variable: `x`\n"
            "  --> services/speccheck/src/lib.rs:42:15\n"
            "   |\n"
            "   = note: `#[warn(clippy::needless_return)]` on by default\n"
        )
        [w] = parse_warnings(block, "rust")
        self.assertEqual(w.file, "services/speccheck/src/lib.rs")
        self.assertEqual(w.line, 42)
        self.assertEqual(w.col, 15)
        self.assertEqual(w.code, "clippy::needless_return")
        self.assertIn("unused variable", w.message)

    def test_two_blocks_each_parsed(self):
        block = (
            "warning: unused import\n  --> src/a.rs:1:5\n"
            "error[E0308]: mismatched types\n  --> src/b.rs:9:1\n"
        )
        warnings = parse_warnings(block, "rust")
        self.assertEqual(len(warnings), 2)
        self.assertEqual(warnings[1].severity, "error")

    def test_non_location_lines_excluded(self):
        self.assertEqual(parse_warnings("    let x = 5;", "rust"), [])

    def test_strips_ansi_colour_codes(self):
        block = "\x1b[0;35mwarning:\x1b[0m unused\n  --> src/a.rs:1:1\n"
        [w] = parse_warnings(block, "rust")
        self.assertEqual(w.severity, "warning")
        self.assertEqual(w.file, "src/a.rs")

    def test_header_code_is_kept_not_overwritten_by_note(self):
        # An rustc error already carries its own code (E0308); a later clippy
        # note line must NOT overwrite that existing code.
        block = (
            "error[E0308]: mismatched types\n"
            "  --> src/b.rs:9:1\n"
            "   = note: `#[warn(clippy::needless_return)]`\n"
        )
        [w] = parse_warnings(block, "rust")
        self.assertEqual(w.code, "E0308")

    def test_note_without_lint_name_leaves_code_empty(self):
        block = (
            "warning: unused variable\n"
            "  --> src/a.rs:1:5\n"
            "   = note: this is just prose, no lint name here\n"
        )
        [w] = parse_warnings(block, "rust")
        self.assertEqual(w.code, "")

    def test_note_before_any_warning_is_ignored(self):
        # A note line with nothing preceding it must not crash or add a row.
        self.assertEqual(
            parse_warnings("   = note: `#[warn(clippy::foo)]`\n", "rust"), []
        )

    def test_arrow_without_header_defaults_to_warning(self):
        [w] = parse_warnings("  --> src/lone.rs:3:2\n", "rust")
        self.assertEqual(w.severity, "warning")
        self.assertEqual(w.message, "")
        self.assertEqual(w.code, "")
        self.assertEqual(w.line, 3)
        self.assertEqual(w.col, 2)


class GeneralParserTests(SimpleTestCase):
    def test_removed_languages_return_empty(self):
        for language in ("cpp", "go", "haskell", "cobol"):
            self.assertEqual(parse_warnings("x:1:1: warning: y", language), [])

    def test_returns_compiler_warning_instances(self):
        line = "warning: x\n  --> src/a.rs:1:1\n"
        for w in parse_warnings(line, "rust"):
            self.assertIsInstance(w, CompilerWarning)

    def test_multiple_lines_each_parsed(self):
        text = "warning: one\n  --> src/a.rs:1:1\nwarning: two\n  --> src/b.rs:2:2\n"
        self.assertEqual(len(parse_warnings(text, "rust")), 2)
