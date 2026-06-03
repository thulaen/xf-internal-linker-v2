"""Convention SimpleTestCase guards for build_failures pure helpers.

These run with NO database: every assertion targets a pure function that turns a
``BuildFailure`` dataclass (or a loose payload dict) into a fingerprint, a
signature line, a title, an affected-files list, or a compressed payload. The
EXACT assertEqual / assertIn checks below are written to kill mutation survivors
on the changed string literals, regex replacements, and slice bounds.
"""

from __future__ import annotations

import json

import lz4.frame
from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.build_failures import (
    BuildFailure,
    _affected_files,
    _combined_output,
    _compress_payload,
    _description,
    _fingerprint,
    _normalize_line,
    _payload,
    _signature_line,
    _title,
    failure_from_payload,
)


def _failure(**overrides) -> BuildFailure:
    base = dict(
        builder="mint",
        targets=["backend"],
        command=["docker", "compose", "build"],
        exit_code=1,
        stdout="",
        stderr="",
    )
    base.update(overrides)
    return BuildFailure(**base)


class CombinedOutputTests(SimpleTestCase):
    def test_joins_stdout_and_stderr_with_newline_and_strips(self):
        failure = _failure(stdout="out", stderr="err")
        self.assertEqual(_combined_output(failure), "out\nerr")

    def test_empty_streams_collapse_to_empty_string(self):
        self.assertEqual(_combined_output(_failure()), "")


class NormalizeLineTests(SimpleTestCase):
    def test_lowercases_and_replaces_line_and_column_numbers(self):
        line = "ERROR at 12:34 in foo"
        self.assertEqual(_normalize_line(line), "error at <line> in foo")

    def test_replaces_line_word_form(self):
        self.assertEqual(_normalize_line("Fatal line 99 here"), "fatal <line> here")

    def test_truncates_to_500_chars(self):
        self.assertEqual(len(_normalize_line("a" * 600)), 500)


class SignatureLineTests(SimpleTestCase):
    def test_picks_first_error_matching_line(self):
        failure = _failure(stderr="all fine\nerror: bad symbol\ntrailing")
        self.assertEqual(_signature_line(failure), "error: bad symbol")

    def test_matches_undefined_keyword(self):
        failure = _failure(stderr="undefined reference to main")
        self.assertEqual(_signature_line(failure), "undefined reference to main")

    def test_falls_back_to_last_line_when_no_error_keyword(self):
        failure = _failure(stderr="line one\nline two")
        self.assertEqual(_signature_line(failure), "line two")

    def test_empty_output_yields_unknown_failure(self):
        self.assertEqual(_signature_line(_failure()), "unknown failure")


class FingerprintTests(SimpleTestCase):
    def test_is_deterministic_and_32_hex_chars(self):
        failure = _failure(stderr="error: boom")
        first = _fingerprint(failure)
        self.assertEqual(first, _fingerprint(failure))
        self.assertEqual(len(first), 32)

    def test_exit_code_changes_fingerprint(self):
        a = _fingerprint(_failure(exit_code=1, stderr="error: boom"))
        b = _fingerprint(_failure(exit_code=2, stderr="error: boom"))
        self.assertNotEqual(a, b)

    def test_targets_are_sorted_so_order_does_not_matter(self):
        a = _fingerprint(_failure(targets=["backend", "frontend"], stderr="error: x"))
        b = _fingerprint(_failure(targets=["frontend", "backend"], stderr="error: x"))
        self.assertEqual(a, b)


class TitleTests(SimpleTestCase):
    def test_includes_targets_and_builder_exactly(self):
        failure = _failure(targets=["backend", "frontend"], builder="desktop-linux")
        self.assertEqual(
            _title(failure),
            "Compilation failed on backend, frontend via desktop-linux",
        )

    def test_empty_targets_render_all_placeholder(self):
        self.assertEqual(
            _title(_failure(targets=[])),
            "Compilation failed on <all> via mint",
        )


class AffectedFilesTests(SimpleTestCase):
    def test_extracts_first_repo_relative_path(self):
        failure = _failure(stderr="error in backend/apps/foo.py:10")
        self.assertEqual(_affected_files(failure), ["backend/apps/foo.py"])

    def test_normalizes_windows_backslashes(self):
        failure = _failure(stderr="error services\\streamd\\main.go")
        self.assertEqual(_affected_files(failure), ["services/streamd/main.go"])

    def test_returns_empty_when_no_path(self):
        self.assertEqual(_affected_files(_failure(stderr="no path here")), [])


class DescriptionTests(SimpleTestCase):
    def test_includes_builder_targets_exit_and_fingerprint(self):
        failure = _failure(builder="mint", targets=["backend"], exit_code=7)
        text = _description(failure, "abc123")
        self.assertIn("Builder: mint", text)
        self.assertIn("Targets: backend", text)
        self.assertIn("Exit code: 7", text)
        self.assertIn("Fingerprint: abc123", text)


class FailureFromPayloadTests(SimpleTestCase):
    def test_defaults_fill_missing_fields(self):
        failure = failure_from_payload({})
        self.assertEqual(failure.builder, "unknown")
        self.assertEqual(failure.targets, ["<all>"])
        self.assertEqual(failure.command, [])
        self.assertEqual(failure.exit_code, 1)

    def test_coerces_types(self):
        failure = failure_from_payload(
            {"builder": 5, "targets": [1, 2], "exit_code": "3"}
        )
        self.assertEqual(failure.builder, "5")
        self.assertEqual(failure.targets, ["1", "2"])
        self.assertEqual(failure.exit_code, 3)


class PayloadTests(SimpleTestCase):
    def test_alert_type_and_severity_are_exact(self):
        payload = _payload(_failure(stderr="error: boom"), "fp1")
        self.assertEqual(payload["alert_type"], "compilation_failure")
        self.assertEqual(payload["severity"], AutoIssue.SEVERITY_HIGH)
        self.assertEqual(payload["true_positive_status"], "needs review")
        self.assertEqual(payload["fingerprint"], "fp1")

    def test_reproduction_command_joins_command_with_spaces(self):
        payload = _payload(_failure(command=["go", "build", "./..."]), "fp")
        self.assertEqual(payload["reproduction_command"], "go build ./...")


class CompressPayloadTests(SimpleTestCase):
    def test_roundtrips_and_reports_byte_sizes(self):
        failure = _failure(stderr="error: boom")
        compressed, raw_len, comp_len = _compress_payload(failure, "fp")
        decoded = json.loads(lz4.frame.decompress(compressed))
        self.assertEqual(decoded["alert_type"], "compilation_failure")
        self.assertEqual(comp_len, len(compressed))
        self.assertGreater(raw_len, 0)
