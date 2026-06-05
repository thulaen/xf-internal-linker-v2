#!/usr/bin/env python3
"""Tests for check-spec-citation.py (Rule C hard-block)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

VALID_SPEC_PROOF = (
    "[SPEC PROOF: specs=docs/specs/example.md "
    "source_types=technical_literature checked_at=2026-05-16 status=current]"
)
VALID_BDD = "[BDD PROOF: Given code changes When commit runs Then specs are checked]"
VALID_TDD = "[TDD PROOF: before_or_alongside=yes tests=spec-hook-tests result=passed]"
VALID_REVIEW = "[SPEC CODE REVIEW: specs=docs/specs/example.md result=matched]"
VALID_RESEARCH = (
    "[SPEC RESEARCH GATE: scope=spec-hook specs=docs/specs/example.md "
    "coverage=full gaps=none research=none]"
)
VALID_HANDOFF = "\n".join(
    (VALID_SPEC_PROOF, VALID_BDD, VALID_TDD, VALID_REVIEW, VALID_RESEARCH)
)
VALID_SPEC_TEXT = "\n".join(
    (
        "# Example",
        "[SPEC CITED: feature=example kind=technical_literature "
        "id=https://example.com/spec verified_at=2026-05-16]",
        "[SPEC FRESHNESS: reviewed_at=2026-05-16 next_review=2026-06-16]",
    )
)


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_spec_citation", here / "check-spec-citation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SpecCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_no_new_specs_passes(self):
        with mock.patch.object(self.hook, "_staged_new_specs", return_value=[]), \
             mock.patch.object(self.hook, "_staged_code_files", return_value=[]):
            self.assertEqual(self.hook.main(), 0)

    def test_staged_helpers_filter_specs_code_and_handoff(self):
        outputs = {
            ("diff", "--cached", "--name-only", "--diff-filter=A"): (
                "docs/specs/a.md\ndocs/specs/_spec-template.md\nREADME.md\n"
            ),
            ("diff", "--cached", "--name-only", "--diff-filter=ACM"): (
                "backend/app.py\ndocker-compose.yml\ndocs/specs/a.md\n"
            ),
            ("diff", "--cached", "--unified=0", "--", "AGENT-HANDOFF.md"): (
                "+++ b/AGENT-HANDOFF.md\n+[SPEC PROOF: specs=docs/specs/a.md]\n"
            ),
        }

        def fake_git(args):
            return subprocess.CompletedProcess(args, 0, outputs[tuple(args)], "")

        with mock.patch.object(self.hook, "_git_output", side_effect=fake_git):
            self.assertEqual(self.hook._staged_new_specs(), ["docs/specs/a.md"])
            self.assertEqual(
                self.hook._staged_code_files(),
                ["backend/app.py", "docker-compose.yml"],
            )
            self.assertIn("SPEC PROOF", self.hook._staged_handoff_diff())

    def test_git_output_handles_timeout(self):
        with mock.patch.object(self.hook.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("git", 1)):
            result = self.hook._git_output(["status"])
        self.assertEqual(result.stdout, "")

    def test_spec_without_citation_fails(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "docs/specs/example.md"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text("# Example\n\nNo citation here.", encoding="utf-8")
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_new_specs",
                                   return_value=["docs/specs/example.md"]), \
                 mock.patch.object(self.hook, "_staged_code_files", return_value=[]), \
                 mock.patch.object(sys, "stderr", StringIO()) as err:
                self.assertEqual(self.hook.main(), 2)
                msg = err.getvalue()
                self.assertIn("FAIL", msg)
                self.assertIn("WHY", msg)
                self.assertIn("UNBLOCK", msg)

    def test_spec_with_citation_passes(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "docs/specs/example.md"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(VALID_SPEC_TEXT, encoding="utf-8")
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_new_specs",
                                   return_value=["docs/specs/example.md"]), \
                 mock.patch.object(self.hook, "_staged_code_files", return_value=[]), \
                 mock.patch.object(self.hook, "_today", return_value=date(2026, 5, 16)):
                self.assertEqual(self.hook.main(), 0)

    def test_new_spec_without_monthly_freshness_fails(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "docs/specs/example.md"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(VALID_SPEC_TEXT.splitlines()[1], encoding="utf-8")
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_new_specs",
                                   return_value=["docs/specs/example.md"]), \
                 mock.patch.object(self.hook, "_staged_code_files", return_value=[]), \
                 mock.patch.object(sys, "stderr", StringIO()) as err:
                self.assertEqual(self.hook.main(), 2)
                self.assertIn("SPEC FRESHNESS", err.getvalue())

    def test_code_change_without_spec_proof_fails(self):
        code, err = self._run_code_gate(["backend/apps/core/example.py"], "")
        self.assertEqual(code, 2)
        self.assertIn("SPEC PROOF", err)

    def test_code_change_requires_bdd_tdd_and_spec_review(self):
        code, err = self._run_code_gate(
            [".githooks/check-spec-citation.py"],
            VALID_SPEC_PROOF,
        )
        self.assertEqual(code, 2)
        self.assertIn("BDD PROOF", err)

    def test_code_change_requires_tdd_proof(self):
        handoff = "\n".join((VALID_SPEC_PROOF, VALID_BDD, VALID_REVIEW))
        code, err = self._run_code_gate(["scripts/example.py"], handoff)
        self.assertEqual(code, 2)
        self.assertIn("TDD PROOF", err)

    def test_code_change_requires_spec_code_review(self):
        handoff = "\n".join((VALID_SPEC_PROOF, VALID_BDD, VALID_TDD, VALID_RESEARCH))
        code, err = self._run_code_gate(["services/example.go"], handoff)
        self.assertEqual(code, 2)
        self.assertIn("SPEC CODE REVIEW", err)

    def test_code_change_requires_spec_research_gate(self):
        handoff = "\n".join((VALID_SPEC_PROOF, VALID_BDD, VALID_TDD, VALID_REVIEW))
        code, err = self._run_code_gate(["backend/apps/core/example.py"], handoff)
        self.assertEqual(code, 2)
        self.assertIn("SPEC RESEARCH GATE", err)

    def test_code_change_rejects_invalid_spec_research_gate_values(self):
        invalid_cases = (
            (
                VALID_HANDOFF.replace("coverage=full", "coverage=missing"),
                "coverage",
            ),
            (
                VALID_HANDOFF.replace("gaps=none", "gaps=open"),
                "gaps",
            ),
            (
                VALID_HANDOFF.replace("gaps=none", "gaps=filled"),
                "research",
            ),
            (
                VALID_HANDOFF.replace(
                    "SPEC RESEARCH GATE: scope=spec-hook specs=docs/specs/example.md",
                    "SPEC RESEARCH GATE: scope=spec-hook specs=docs/specs/other.md",
                ),
                "cover every spec",
            ),
        )
        for handoff, expected in invalid_cases:
            with self.subTest(expected=expected):
                code, err = self._run_code_gate(["backend/apps/core/example.py"], handoff)
                self.assertEqual(code, 2)
                self.assertIn(expected, err)

    def test_code_change_rejects_incomplete_spec_proof_fields(self):
        code, err = self._run_code_gate(
            ["backend/apps/core/example.py"],
            "[SPEC PROOF: specs=docs/specs/example.md]",
        )
        self.assertEqual(code, 2)
        self.assertIn("missing field", err)

    def test_code_change_rejects_invalid_spec_proof_values(self):
        invalid_cases = (
            ("checked_at=bad", "current month"),
            ("status=old", "status"),
            ("source_types=blog", "technical_literature"),
            ("specs=,", "at least one spec"),
        )
        for replacement, expected in invalid_cases:
            with self.subTest(replacement=replacement):
                handoff = VALID_HANDOFF
                if replacement.startswith("checked_at"):
                    handoff = handoff.replace("checked_at=2026-05-16", replacement)
                elif replacement.startswith("status"):
                    handoff = handoff.replace("status=current", replacement)
                elif replacement.startswith("source_types"):
                    handoff = handoff.replace("source_types=technical_literature", replacement)
                else:
                    handoff = handoff.replace("specs=docs/specs/example.md", replacement)
                code, err = self._run_code_gate(["scripts/example.py"], handoff)
                self.assertEqual(code, 2)
                self.assertIn(expected, err)

    def test_code_change_rejects_invalid_tdd_and_review_values(self):
        cases = (
            (
                VALID_HANDOFF.replace("result=passed", "result=failed"),
                "TDD PROOF must say",
            ),
            (
                VALID_HANDOFF.replace("result=matched", "result=failed"),
                "SPEC CODE REVIEW result",
            ),
            (
                VALID_HANDOFF.replace("SPEC CODE REVIEW: specs=docs/specs/example.md",
                                      "SPEC CODE REVIEW: specs=docs/specs/other.md"),
                "cover every spec",
            ),
        )
        for handoff, expected in cases:
            with self.subTest(expected=expected):
                code, err = self._run_code_gate(["services/example.go"], handoff)
                self.assertEqual(code, 2)
                self.assertIn(expected, err)

    def test_code_change_rejects_missing_or_misplaced_spec_file(self):
        misplaced = VALID_HANDOFF.replace("docs/specs/example.md", "README.md")
        code, err = self._run_code_gate(["backend/apps/core/example.py"], misplaced)
        self.assertEqual(code, 2)
        self.assertIn("docs/specs", err)

        missing = VALID_HANDOFF.replace("docs/specs/example.md", "docs/specs/missing.md")
        code, err = self._run_code_gate(["backend/apps/core/example.py"], missing)
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)

    def test_code_change_rejects_stale_spec_review_month(self):
        stale = VALID_HANDOFF.replace("checked_at=2026-05-16", "checked_at=2026-04-30")
        code, err = self._run_code_gate(["backend/apps/core/example.py"], stale)
        self.assertEqual(code, 2)
        self.assertIn("current month", err)

    def test_code_change_rejects_spec_without_source_backing(self):
        code, err = self._run_code_gate(
            ["backend/apps/core/example.py"],
            VALID_HANDOFF,
            spec_text="# Example\n[SPEC FRESHNESS: reviewed_at=2026-05-16 next_review=2026-06-16]",
        )
        self.assertEqual(code, 2)
        self.assertIn("source-backed", err)

    def test_code_change_passes_with_current_source_backed_spec(self):
        code, _ = self._run_code_gate(["backend/apps/core/example.py"], VALID_HANDOFF)
        self.assertEqual(code, 0)

    def _run_code_gate(
        self,
        staged_files: list[str],
        handoff: str,
        spec_text: str = VALID_SPEC_TEXT,
    ) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "docs/specs/example.md"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(spec_text, encoding="utf-8")
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_new_specs", return_value=[]), \
                 mock.patch.object(self.hook, "_staged_code_files",
                                   return_value=staged_files), \
                 mock.patch.object(self.hook, "_staged_handoff_diff",
                                   return_value=handoff), \
                 mock.patch.object(self.hook, "_today", return_value=date(2026, 5, 16)), \
                 mock.patch.object(sys, "stderr", StringIO()) as err:
                return self.hook.main(), err.getvalue()


if __name__ == "__main__":
    unittest.main(verbosity=2)
