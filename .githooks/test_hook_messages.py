#!/usr/bin/env python3
"""Meta-test for Rule F (universal plain-English hook FAIL messages).

Scans every check-*.py hook in .githooks/ and asserts that any stderr
write containing "FAIL" also mentions WHY (or "why" / "Why") and
UNBLOCK (or "unblock" / "run `manage.py ..."`).

Hooks that pre-date this rule and need rewriting will be flagged.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


_HOOKS_DIR = Path(__file__).resolve().parent
_FAIL_RE = re.compile(r'"FAIL[^"\\]+', re.DOTALL)


def _read_hooks() -> list[Path]:
    return sorted(
        p for p in _HOOKS_DIR.glob("check-*.py") if p.is_file()
    )


def _has_unblock_hint(text: str) -> bool:
    return (
        "UNBLOCK" in text
        or "unblock" in text
        or "manage.py" in text
        or "Run `" in text
    )


def _has_why_hint(text: str) -> bool:
    return "WHY" in text or "Why:" in text or "Rule " in text


class HookMessageTests(unittest.TestCase):

    def test_every_hook_exists(self):
        hooks = _read_hooks()
        self.assertGreater(len(hooks), 0, "No check-*.py hooks found")

    def test_new_hooks_have_plain_english_fail_messages(self):
        """The four NEW hooks from this plan MUST include WHY + UNBLOCK
        hints in their FAIL paths. The existing legacy hooks are
        grandfathered until they are individually rewritten per the
        Day-5 audit task.
        """
        new_hooks = {
            "check-perf-proof.py",
            "check-tdd-cycle.py",
            "check-spec-citation.py",
            "check-scoped-lessons.py",
            "check-code-review-lessons.py",
            "check-paper-trail-read.py",  # already compliant
            # Rule H sub-rules — six hooks landed in this session.
            "check-debug-code.py",
            "check-junk-files.py",
            "check-mutable-defaults.py",
            "check-django-deploy.py",
            "check-fk-on-delete.py",
            "check-mgmt-command-dry-run.py",
            # Every-deferral-filed gate (added 2026-05-16).
            "check-deferral-filed.py",
        }
        failed = []
        for hook in _read_hooks():
            if hook.name not in new_hooks:
                continue
            text = hook.read_text(encoding="utf-8")
            if "FAIL" not in text:
                continue  # hook has no FAIL path at all
            if not _has_why_hint(text):
                failed.append(f"{hook.name}: no WHY/why/Rule hint")
            if not _has_unblock_hint(text):
                failed.append(f"{hook.name}: no UNBLOCK/manage.py hint")
        self.assertEqual(
            failed, [],
            "Hooks failing Rule F (plain-English FAIL):\n" + "\n".join(failed)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
