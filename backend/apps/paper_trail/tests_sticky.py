"""Regression tests for the Sticky #1 system (Phase K.1, 2026-05-23).

Covers three production-source changes that ship together:

* `PaperTrailEntry.STATUS_STICKY` + the 10,000-word cap exemption and
  the BDD / evidence-rule short-circuit on sticky entries.
* `manage.py read_sticky` printing the SHA-256-verified marker.
* `manage.py log_sticky` filing a sticky from an on-disk body file.
"""
from __future__ import annotations

import hashlib
import tempfile
from io import StringIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from apps.paper_trail.models import PaperTrailEntry


def _sticky_kwargs(**overrides) -> dict:
    """Return the minimum kwargs needed to construct a STATUS_STICKY row."""
    defaults = {
        "title": "Test sticky",
        "abstract": "Body without BDD shape, no risk_on_inaction, no acceptance_criteria.",
        "category": PaperTrailEntry.CATEGORY_DOCUMENTATION,
        "severity": PaperTrailEntry.SEVERITY_CRITICAL,
        "status": PaperTrailEntry.STATUS_STICKY,
        "deferred_by": "user",
    }
    defaults.update(overrides)
    return defaults


class StickyModelValidationTests(TestCase):
    """Sticky entries bypass the standard validation rules."""

    def test_sticky_accepts_long_abstract_up_to_ten_thousand_words(self) -> None:
        body = " ".join(["word"] * 5_000)  # 5k words, well above 1200 cap
        entry = PaperTrailEntry(**_sticky_kwargs(abstract=body))
        entry._validate()  # must not raise

    def test_sticky_rejects_abstract_above_ten_thousand_words(self) -> None:
        body = " ".join(["word"] * 10_001)
        entry = PaperTrailEntry(**_sticky_kwargs(abstract=body))
        with self.assertRaises(ValidationError) as ctx:
            entry._validate()
        self.assertIn("10000", str(ctx.exception))

    def test_sticky_bypasses_bdd_requirement(self) -> None:
        # Non-sticky entries with a non-BDD abstract would raise; sticky
        # entries do not.
        entry = PaperTrailEntry(
            **_sticky_kwargs(abstract="Plain prose, no Given/When/Then.")
        )
        entry._validate()  # must not raise

    def test_non_sticky_still_hits_the_twelve_hundred_word_cap(self) -> None:
        body = " ".join(["word"] * 1_500)
        entry = PaperTrailEntry(
            title="Non-sticky",
            abstract=body,
            category=PaperTrailEntry.CATEGORY_DOCUMENTATION,
            severity=PaperTrailEntry.SEVERITY_MEDIUM,
            status=PaperTrailEntry.STATUS_OPEN,
            deferred_by="claude",
        )
        with self.assertRaises(ValidationError) as ctx:
            entry._validate()
        self.assertIn("1200", str(ctx.exception))


class LogStickyCommandTests(TestCase):
    """`manage.py log_sticky` creates and updates sticky rows."""

    def _abstract_file(self, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            delete=False,
            encoding="utf-8",
        )
        tmp.write(body)
        tmp.close()
        return Path(tmp.name)

    def test_log_sticky_creates_a_new_sticky(self) -> None:
        body = " ".join(["word"] * 100)
        path = self._abstract_file(body)
        out = StringIO()
        call_command(
            "log_sticky",
            "--title",
            "Test sticky created via command",
            "--abstract-file",
            str(path),
            stdout=out,
        )
        self.assertIn("STICKY FILED", out.getvalue())
        entry = PaperTrailEntry.objects.get(
            title="Test sticky created via command"
        )
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_STICKY)
        self.assertEqual(entry.abstract, body)


class ReadStickyCommandTests(TestCase):
    """`manage.py read_sticky` prints the SHA-256-verified marker."""

    def test_read_sticky_prints_marker_with_sha_prefix(self) -> None:
        body = " ".join(["word"] * 50)
        entry = PaperTrailEntry.objects.create(
            **_sticky_kwargs(
                title="Sticky for read test",
                abstract=body,
            )
        )
        expected_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

        out = StringIO()
        call_command("read_sticky", "--id", "1", stdout=out)
        output = out.getvalue()
        self.assertIn(f"sha256={expected_sha}", output)
        self.assertIn("[STICKY 1 READ:", output)

    def test_print_sha_only_prints_just_the_prefix(self) -> None:
        body = "hello world"
        PaperTrailEntry.objects.create(
            **_sticky_kwargs(
                title="Sticky for sha-only test",
                abstract=body,
            )
        )
        expected_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

        out = StringIO()
        call_command("read_sticky", "--id", "1", "--print-sha-only", stdout=out)
        self.assertEqual(out.getvalue().strip(), expected_sha)
