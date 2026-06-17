#!/usr/bin/env python3
"""Tests for the multi-scope, config-driven ELCV exporter. Run:
    python tools/elcv/test_exporters.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exporters  # noqa: E402

CFG = {
    "global_ceiling": 2000000000,
    "scopes": {
        "repo": {"target": 2000000000, "roots": []},
        "ranklab": {"target": 28000000, "roots": []},
        "aegis": {"target": 5000000, "roots": []},
    },
}


class ScopeMathTests(unittest.TestCase):
    def test_scope_math_from_real_code(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "m.py").write_text("def f(x):\n    if x:\n        return 1\n    return 0\n",
                                       encoding="utf-8")
            rep = exporters.scope_report("demo", {"target": 100, "roots": [d]})
        self.assertEqual(rep["target"], 100)
        self.assertGreater(rep["current"], 0)
        self.assertAlmostEqual(rep["percent"], round(100 * rep["current"] / 100, 6))
        self.assertAlmostEqual(rep["remaining"], 100 - rep["current"])

    def test_targets_come_from_config_not_hardcoded(self):
        rep = exporters.full_report(now="2026-01-01T00:00:00", config=CFG)
        self.assertEqual(rep["global_ceiling"], 2_000_000_000)
        self.assertEqual(rep["scopes"]["ranklab"]["target"], 28_000_000)
        self.assertEqual(rep["scopes"]["aegis"]["target"], 5_000_000)

    def test_status_is_measured_not_pending(self):
        # ELCV no longer depends on runtime data (ARW removed) -> measured, never "pending".
        self.assertEqual(exporters.full_report(now="t", config=CFG)["status"], "measured")

    def test_empty_scope_is_zero(self):
        rep = exporters.full_report(now="t", config=CFG)
        self.assertEqual(rep["scopes"]["ranklab"]["current"], 0)
        self.assertEqual(rep["scopes"]["ranklab"]["percent"], 0.0)

    def test_prometheus_has_per_scope_metrics(self):
        text = exporters.to_prometheus(now="t", config=CFG)
        self.assertIn("elcv_global_ceiling 2000000000", text)
        self.assertIn('elcv_scope_target{scope="ranklab"} 28000000', text)
        self.assertIn('elcv_scope_target{scope="aegis"} 5000000', text)
        self.assertIn('elcv_scope_percent{scope="ranklab"}', text)

    def test_board_lists_every_scope(self):
        board = exporters.to_board_markdown(now="t", config=CFG)
        for name in ("repo", "ranklab", "aegis"):
            self.assertIn(name, board)
        self.assertIn("2,000,000,000", board)   # the global ceiling


if __name__ == "__main__":
    unittest.main(verbosity=2)
