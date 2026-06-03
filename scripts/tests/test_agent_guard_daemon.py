"""Convention tests for scripts/agent_guard_daemon.py debounce + dir filter.

BDD:
  Given a GuardEventHandler with a known debounce window
  When should_check is called repeatedly for the same path
  Then non-source paths are rejected, the first source event passes, a second
       event inside the debounce window is rejected, and an event after the
       window passes again — killing mutation survivors on the debounce maths.

watchdog is required by the module; if it is unavailable the suite skips rather
than failing the unrelated import.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


try:
    agd = _load("agent_guard_daemon", "agent_guard_daemon.py")
except Exception:  # noqa: BLE001 — watchdog missing in this image is a skip, not a fail
    agd = None


class TestShouldCheck(TestCase):
    def setUp(self):
        if agd is None:
            self.skipTest("watchdog unavailable in this image")

    def test_non_source_path_rejected(self):
        h = agd.GuardEventHandler(debounce_seconds=1.0)
        self.assertFalse(h.should_check("notes.txt", now=100.0))

    def test_first_source_event_passes(self):
        h = agd.GuardEventHandler(debounce_seconds=1.0)
        self.assertTrue(h.should_check("backend/x.py", now=100.0))

    def test_second_event_within_window_rejected(self):
        h = agd.GuardEventHandler(debounce_seconds=1.0)
        h.should_check("backend/x.py", now=100.0)
        self.assertFalse(h.should_check("backend/x.py", now=100.5))

    def test_event_after_window_passes(self):
        h = agd.GuardEventHandler(debounce_seconds=1.0)
        h.should_check("backend/x.py", now=100.0)
        self.assertTrue(h.should_check("backend/x.py", now=101.5))
