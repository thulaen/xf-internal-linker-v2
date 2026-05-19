r"""Tests for .githooks/check-session-close.py.

Session S4 of the PARAMOUNT TDD-pipeline rule. The hook HARD-BLOCKS
the FIRST code-changing commit of a NEW session if the prior session's
final handoff entry lacks a `[SESSION CLOSE: …]` marker.

Detection of "first commit of a new session": the staged
AGENT-HANDOFF.md diff adds a new top-level session header
(line matching `^# \d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+-\s+`).
Otherwise the gate stays quiet so subsequent commits within the same
session don't keep firing it.

Exemptions:
  * Pure-docs / generated-only commits.
  * Rule-introduction commit (docs/TDD-PIPELINE-RULE.md is staged).

Written FIRST (Red) per the strict-TDD rule the pipeline enforces.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    hook_path = HOOKS_DIR / "check-session-close.py"
    spec = importlib.util.spec_from_file_location("check_session_close", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_session_close"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _capture_stderr(func, *args, **kwargs):
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


_NEW_SESSION_DIFF = (
    "# 2026-05-18 02:00 - Claude Opus 4.7 - Session S4 starts here\n"
    "[HANDOFF READ: 2026-05-17 18:00 by Claude — prior session]\n"
)

_PRIOR_HANDOFF_WITH_CLOSE = """\
# 2026-05-17 18:00 - Claude Opus 4.7 - Prior session

[HANDOFF READ: ...]
[SESSION CLOSE: lessons_verified=3 artefacts_pruned_mb=0.0 prefixes=mull,coverage,mutmut,stryker,fuzz-work,pytest-debug closed_at=2026-05-17T22:00:00Z]
"""

_PRIOR_HANDOFF_NO_CLOSE = """\
# 2026-05-17 18:00 - Claude Opus 4.7 - Prior session

[HANDOFF READ: ...]
(no SESSION CLOSE marker — agent forgot to close)
"""


class NewSessionDetectionTests(TestCase):

    def test_new_session_with_prior_close_passes(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_session_close,
            head_handoff=_PRIOR_HANDOFF_WITH_CLOSE,
            staged_handoff_diff=_NEW_SESSION_DIFF,
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 0, msg=err)

    def test_new_session_without_prior_close_fails(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_session_close,
            head_handoff=_PRIOR_HANDOFF_NO_CLOSE,
            staged_handoff_diff=_NEW_SESSION_DIFF,
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 2)
        self.assertIn("SESSION CLOSE", err)

    def test_staged_prior_close_passes_even_when_head_lacks_it(self) -> None:
        staged_full = (
            "# 2026-05-18 02:00 - Codex - Current session\n"
            "[HANDOFF READ: 2026-05-17 18:00 by Claude — prior session]\n\n"
            + _PRIOR_HANDOFF_WITH_CLOSE
        )
        rv, err = _capture_stderr(
            hook.validate_session_close,
            head_handoff=_PRIOR_HANDOFF_NO_CLOSE,
            staged_handoff_diff=_NEW_SESSION_DIFF,
            staged_files=["backend/apps/x.py"],
            staged_handoff_full=staged_full,
        )
        self.assertEqual(rv, 0, msg=err)

    def test_mid_session_commit_does_not_fire(self) -> None:
        # No new session header in staged diff → hook stays quiet.
        diff_without_new_header = (
            "[TDD CYCLE STRICT: ...]\n[TEST CASE MAPPING: ...]\n"
        )
        rv, err = _capture_stderr(
            hook.validate_session_close,
            head_handoff=_PRIOR_HANDOFF_NO_CLOSE,
            staged_handoff_diff=diff_without_new_header,
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 0, msg=err)


class ExemptionTests(TestCase):

    def test_pure_docs_commit_is_exempt(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_session_close,
            head_handoff=_PRIOR_HANDOFF_NO_CLOSE,
            staged_handoff_diff=_NEW_SESSION_DIFF,
            staged_files=["docs/foo.md", "README.md"],
        )
        self.assertEqual(rv, 0, msg=err)

    def test_no_staged_files_is_exempt(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_session_close,
            head_handoff=_PRIOR_HANDOFF_NO_CLOSE,
            staged_handoff_diff="",
            staged_files=[],
        )
        self.assertEqual(rv, 0, msg=err)

    def test_rule_introduction_commit_grandfathered(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_session_close,
            head_handoff=_PRIOR_HANDOFF_NO_CLOSE,
            staged_handoff_diff=_NEW_SESSION_DIFF,
            staged_files=["docs/TDD-PIPELINE-RULE.md", "backend/apps/x.py"],
        )
        self.assertEqual(rv, 0, msg=err)


class PriorBlockExtractionTests(TestCase):

    def test_extracts_first_session_block(self) -> None:
        text = """\
# 2026-05-17 18:00 - Claude - Latest

Some content
[SESSION CLOSE: foo]

# 2026-05-16 09:30 - Codex - Older session
content
"""
        block = hook._first_handoff_block(text)
        self.assertIn("2026-05-17 18:00", block)
        self.assertIn("[SESSION CLOSE: foo]", block)
        self.assertNotIn("2026-05-16", block)

    def test_returns_full_text_when_no_second_block(self) -> None:
        text = "# 2026-05-17 18:00 - Solo session\n[SESSION CLOSE: x]\n"
        block = hook._first_handoff_block(text)
        self.assertIn("[SESSION CLOSE: x]", block)

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(hook._first_handoff_block(""), "")


if __name__ == "__main__":
    unittest.main()
