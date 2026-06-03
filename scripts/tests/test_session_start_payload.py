"""Tests for scripts/session_start_payload.py.

BDD:
  Given startupd is unreachable
  When _check_health() runs
  Then it exits with the plain-English down message

  Given a healthy /gate endpoint
  When _call_gate() runs
  Then it returns the parsed JSON dict
"""

from __future__ import annotations

import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest import TestCase, mock
from urllib.error import URLError

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "session_start_payload.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_start_payload", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["session_start_payload"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()


class _FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class TestValidSessionTypes(TestCase):
    def test_exact_set(self) -> None:
        self.assertEqual(
            m._VALID_SESSION_TYPES,
            ("docs", "infrastructure", "reconciliation", "feature"),
        )


class TestDownMessage(TestCase):
    def test_names_url_and_fix_command(self) -> None:
        msg = m._DOWN_MSG.format(url="http://127.0.0.1:8765")
        self.assertIn("http://127.0.0.1:8765/health", msg)
        self.assertIn("docker compose up -d startupd", msg)


class TestCheckHealth(TestCase):
    def test_exits_when_unreachable(self) -> None:
        with mock.patch.object(m, "urlopen", side_effect=URLError("down")):
            with self.assertRaises(SystemExit) as ctx:
                m._check_health("http://x", timeout=1.0)
        self.assertIn("startupd is not responding", str(ctx.exception))

    def test_passes_when_reachable(self) -> None:
        with mock.patch.object(m, "urlopen", return_value=_FakeResponse(b"ok")):
            self.assertIsNone(m._check_health("http://x", timeout=1.0))


class TestCallGate(TestCase):
    def test_returns_parsed_json(self) -> None:
        body = json.dumps({"marker_block": "MB", "state": {"a": 1}}).encode("utf-8")
        with mock.patch.object(m, "urlopen", return_value=_FakeResponse(body)):
            result = m._call_gate("http://x", "feature", ["backend/apps"], timeout=1.0)
        self.assertEqual(result["marker_block"], "MB")

    def test_exits_on_request_error(self) -> None:
        with mock.patch.object(m, "urlopen", side_effect=URLError("boom")):
            with self.assertRaises(SystemExit) as ctx:
                m._call_gate("http://x", "feature", [], timeout=1.0)
        self.assertIn("session gate request failed", str(ctx.exception))
