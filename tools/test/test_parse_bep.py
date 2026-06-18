"""Tests for the Bazel event parser."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.parse_bep import summarize


class ParseBepTests(unittest.TestCase):
    def test_counts_failed_test_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bep.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"id": 1}),
                        json.dumps({"testResult": {"status": "FAILED"}}),
                        json.dumps({"testResult": {"status": "PASSED"}}),
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(summarize(path), {"events": 3, "failures": 1})


if __name__ == "__main__":
    unittest.main()
