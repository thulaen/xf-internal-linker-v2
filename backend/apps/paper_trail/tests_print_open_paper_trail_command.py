"""TDD tests for print_open_paper_trail command."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.paper_trail.models import PaperTrailEntry


def _make(**overrides) -> PaperTrailEntry:
    defaults = {
        "category": PaperTrailEntry.CATEGORY_OTHER,
        "title": "to be printed",
        "abstract": (
            "Given the print_open_paper_trail tests need a row, "
            "When _make() constructs one, "
            "Then it passes BDD validation."
        ),
        "deferred_by": "test",
        "risk_on_inaction": "Test only.",
        "acceptance_criteria": "Test passes.",
    }
    defaults.update(overrides)
    return PaperTrailEntry.objects.create(**defaults)


class PrintOpenPaperTrailTests(TestCase):
    def test_emits_marker_with_zero_open(self) -> None:
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        self.assertIn("[PAPER TRAIL READ:", out.getvalue())
        self.assertIn("0 open", out.getvalue())

    def test_emits_marker_with_open_entries(self) -> None:
        _make(category=PaperTrailEntry.CATEGORY_CVE_UPGRADE, title="cve1")
        _make(category=PaperTrailEntry.CATEGORY_RUFF_SWEEP, title="ruff1")
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        text = out.getvalue()
        self.assertIn("[PAPER TRAIL READ:", text)
        self.assertIn("2 open", text)
        self.assertIn("1 cve_upgrade", text)
        self.assertIn("1 ruff_sweep", text)

    def test_breakdown_lists_all_16_categories(self) -> None:
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        for cat, _label in PaperTrailEntry.CATEGORY_CHOICES:
            self.assertIn(cat, out.getvalue())

    def test_drought_form_when_under_10(self) -> None:
        _make(title="only one entry")
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        self.assertIn("drought", out.getvalue())
