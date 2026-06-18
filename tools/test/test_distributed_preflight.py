"""Tests for the distributed preflight shell checklist."""

from __future__ import annotations

from pathlib import Path
import re
from unittest import TestCase


class TestDistributedPreflight(TestCase):
    def test_preflight_script_lists_twelve_checks(self) -> None:
        text = Path("tools/preflight/run-distributed-preflight.sh").read_text()
        match = re.search(r"checks=\(\n(?P<body>.*?)\n\)", text, re.S)
        self.assertIsNotNone(match)
        checks = [line.strip() for line in match.group("body").splitlines()]
        self.assertEqual(len(checks), 12)
        self.assertIn("msi-docker-free", checks)
