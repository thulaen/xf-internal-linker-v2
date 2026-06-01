"""Tests for the pure compiler/linter warning parser (no DB, no network).

Covers C++ (clang/gcc), Go (go vet / golangci-lint), Rust (cargo / clippy
arrow-location), and Haskell (GHC / hlint). Each language has one realistic
fixture asserting the parsed file/line/code, plus edge cases: blank lines,
ANSI colour codes, Windows paths, and multi-line Rust/GHC blocks. Regex shapes
were designed by the Phase B research fan-out; see
docs/specs/fr-compiler-warning-autoissues.md.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.services.compiler_warnings import (
    CompilerWarning,
    parse_warnings,
)


class CppParserTests(SimpleTestCase):
    def test_parses_clang_warning_with_code(self):
        line = "backend/extensions/simsearch.cpp:42:15: warning: variable 'result' set but not used [-Wunused-variable]"
        [w] = parse_warnings(line, "cpp")
        self.assertEqual(w.file, "backend/extensions/simsearch.cpp")
        self.assertEqual(w.line, 42)
        self.assertEqual(w.col, 15)
        self.assertEqual(w.code, "-Wunused-variable")
        self.assertEqual(w.severity, "warning")
        self.assertIn("set but not used", w.message)

    def test_parses_error_severity(self):
        line = "backend/extensions/scoring.h:87:3: error: unknown type name 'ScoringContext'"
        [w] = parse_warnings(line, "cpp")
        self.assertEqual(w.severity, "error")
        self.assertEqual(w.code, "")

    def test_parses_warning_without_column(self):
        line = "backend/extensions/include/utils.cpp:156: warning: Unused variable 'temp_buffer'"
        [w] = parse_warnings(line, "cpp")
        self.assertEqual(w.line, 156)
        self.assertIsNone(w.col)

    def test_strips_ansi_colour_codes(self):
        line = "a.cpp:1:1: \x1b[0;35mwarning:\x1b[0m dead code [-Wunused]"
        [w] = parse_warnings(line, "cpp")
        self.assertEqual(w.code, "-Wunused")
        self.assertEqual(w.severity, "warning")

    def test_parses_windows_drive_path(self):
        line = r"C:\src\extensions\foo.cpp:9:4: warning: shadowed [-Wshadow]"
        [w] = parse_warnings(line, "cpp")
        self.assertEqual(w.file, r"C:\src\extensions\foo.cpp")
        self.assertEqual(w.line, 9)

    def test_summary_and_blank_lines_do_not_match(self):
        for noise in ("===== build summary =====", "1 warning generated.", "", "   "):
            self.assertEqual(parse_warnings(noise, "cpp"), [])


class GoParserTests(SimpleTestCase):
    def test_parses_go_vet_line(self):
        line = "services/streamd/internal/broker/broker.go:42:5: assignment to entry is never used"
        [w] = parse_warnings(line, "go")
        self.assertEqual(w.file, "services/streamd/internal/broker/broker.go")
        self.assertEqual(w.line, 42)
        self.assertEqual(w.col, 5)
        self.assertIn("never used", w.message)

    def test_parses_golangci_lint_paren_linter(self):
        line = "backend/internal/cache/cache.go:89:8: Error return value not checked (errcheck)"
        [w] = parse_warnings(line, "go")
        self.assertEqual(w.code, "errcheck")
        self.assertIn("not checked", w.message)

    def test_parses_golangci_lint_bracket_linter(self):
        line = "internal/cache/cache.go:7:2: ineffectual assignment to err [ineffassign]"
        [w] = parse_warnings(line, "go")
        self.assertEqual(w.code, "ineffassign")
        self.assertIn("ineffectual", w.message)

    def test_location_only_no_message_excluded(self):
        # A bare "file:line:col:" with no message text must not file a warning.
        self.assertEqual(parse_warnings("foo.go:3:4:    ", "go"), [])

    def test_progress_lines_excluded(self):
        for noise in ("+ go vet ./... in services/streamd", "No issues found", ""):
            self.assertEqual(parse_warnings(noise, "go"), [])


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


class HaskellParserTests(SimpleTestCase):
    def test_parses_ghc_warning_message_then_flag(self):
        line = "services/findbugs-haskell/src/FindBugs/Clustering.hs:42:1: warning: Redundant lambda [-Wredundant-lambdas]"
        [w] = parse_warnings(line, "haskell")
        self.assertEqual(w.file, "services/findbugs-haskell/src/FindBugs/Clustering.hs")
        self.assertEqual(w.line, 42)
        self.assertEqual(w.col, 1)
        self.assertEqual(w.code, "-Wredundant-lambdas")
        self.assertEqual(w.severity, "warning")

    def test_parses_ghc9_flag_then_message(self):
        line = "src/Foo.hs:5:3: warning: [-Wname-shadowing] this binding shadows"
        [w] = parse_warnings(line, "haskell")
        self.assertEqual(w.code, "-Wname-shadowing")
        self.assertIn("shadows", w.message)

    def test_parses_hlint_capital_warning(self):
        line = "src/Bar.hs:10:7: Warning: Use camelCase"
        [w] = parse_warnings(line, "haskell")
        self.assertEqual(w.severity, "warning")
        self.assertIn("camelCase", w.message)

    def test_parses_ghc_error_severity(self):
        line = "src/Baz.hs:3:9: error: Variable not in scope: foo"
        [w] = parse_warnings(line, "haskell")
        self.assertEqual(w.severity, "error")
        self.assertEqual(w.code, "")
        self.assertIn("not in scope", w.message)

    def test_compile_progress_excluded(self):
        self.assertEqual(parse_warnings("[1 of 5] Compiling FindBugs.NullState", "haskell"), [])


class GeneralParserTests(SimpleTestCase):
    def test_unknown_language_returns_empty(self):
        self.assertEqual(parse_warnings("x:1:1: warning: y", "cobol"), [])

    def test_returns_compiler_warning_instances(self):
        line = "a.cpp:1:1: warning: x [-Wall]"
        for w in parse_warnings(line, "cpp"):
            self.assertIsInstance(w, CompilerWarning)

    def test_multiple_lines_each_parsed(self):
        text = "a.go:1:1: msg one\nb.go:2:2: msg two\n"
        self.assertEqual(len(parse_warnings(text, "go")), 2)
