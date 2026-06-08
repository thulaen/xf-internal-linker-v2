#!/usr/bin/env python3
"""Tests for check-xftool-contract.py — the xftool quality gate."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_xftool_contract", Path(__file__).resolve().parent / "check-xftool-contract.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse_catalog = _mod.parse_catalog
contract_violations = _mod.contract_violations

_GOOD_CATALOG = '''
pub const CATALOG: &[CatalogEntry] = &[
    CatalogEntry {
        command: "ranking diff",
        category: "Ranking & scoring validity",
        mutates: false,
        summary: "Diff two ranking-run JSONs.",
    },
    CatalogEntry {
        command: "store gc-report",
        category: "Build & artifact store",
        mutates: false,
        summary: "Report unreferenced SHAs.",
    },
];
'''

_GOOD_CLI = '''
fn x() { run(&["ranking", "diff", a]); run(&["store", "gc-report", f]); }
'''

_GOOD_MODULES = {"ranking": True, "store": True}


class ParseCatalogTests(unittest.TestCase):
    def test_parses_all_rows(self):
        entries = parse_catalog(_GOOD_CATALOG)
        self.assertEqual([e["command"] for e in entries], ["ranking diff", "store gc-report"])
        self.assertEqual(entries[0]["category"], "Ranking & scoring validity")
        self.assertEqual(entries[0]["mutates"], "false")


class ContractTests(unittest.TestCase):
    def test_clean_catalog_has_no_violations(self):
        self.assertEqual(contract_violations(_GOOD_CATALOG, _GOOD_CLI, _GOOD_MODULES), [])

    def test_empty_catalog_is_flagged(self):
        self.assertTrue(contract_violations("// no entries", _GOOD_CLI, _GOOD_MODULES))

    def test_duplicate_command_is_flagged(self):
        dup = _GOOD_CATALOG.replace('"store gc-report"', '"ranking diff"')
        problems = contract_violations(dup, _GOOD_CLI, _GOOD_MODULES)
        self.assertTrue(any("duplicate" in p for p in problems))

    def test_empty_summary_is_flagged(self):
        bad = _GOOD_CATALOG.replace('"Diff two ranking-run JSONs."', '""')
        problems = contract_violations(bad, _GOOD_CLI, _GOOD_MODULES)
        self.assertTrue(any("incomplete catalog row" in p for p in problems))

    def test_missing_module_is_flagged(self):
        problems = contract_violations(_GOOD_CATALOG, _GOOD_CLI, {"store": True})
        self.assertTrue(any("no command module" in p and "ranking" in p for p in problems))

    def test_module_without_cfg_test_is_flagged(self):
        problems = contract_violations(_GOOD_CATALOG, _GOOD_CLI, {"ranking": False, "store": True})
        self.assertTrue(any("no #[cfg(test)]" in p for p in problems))

    def test_command_not_in_e2e_test_is_flagged(self):
        cli = 'fn x() { run(&["ranking", "diff", a]); }'  # store gc-report missing
        problems = contract_violations(_GOOD_CATALOG, cli, _GOOD_MODULES)
        self.assertTrue(any("not exercised by the e2e test" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
