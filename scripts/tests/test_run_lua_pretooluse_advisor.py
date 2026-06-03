"""Tests for scripts/run-lua-pretooluse-advisor.py remote-guard helpers.

BDD:
  Given DOCKER_HOST or a non-desktop DOCKER_CONTEXT
  When _remote_docker_is_active() runs
  Then it returns True (refuse to run the advisor on a remote machine)

  Given the desktop-linux context with no DOCKER_HOST
  When _remote_docker_is_active() runs
  Then it returns False (local Docker Desktop is allowed)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "run-lua-pretooluse-advisor.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "run_lua_pretooluse_advisor", _MODULE_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_lua_pretooluse_advisor"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()


class TestRemoteDockerIsActive(TestCase):
    def test_true_when_docker_host_set(self) -> None:
        with mock.patch.dict(m.os.environ, {"DOCKER_HOST": "tcp://10.10.10.91:2376"}):
            self.assertTrue(m._remote_docker_is_active())

    def test_true_when_remote_context(self) -> None:
        with mock.patch.dict(
            m.os.environ, {"DOCKER_CONTEXT": "mint"}, clear=False
        ):
            m.os.environ.pop("DOCKER_HOST", None)
            self.assertTrue(m._remote_docker_is_active())

    def test_false_for_desktop_linux(self) -> None:
        with mock.patch.dict(
            m.os.environ, {"DOCKER_CONTEXT": "desktop-linux"}, clear=False
        ):
            m.os.environ.pop("DOCKER_HOST", None)
            self.assertFalse(m._remote_docker_is_active())

    def test_false_when_nothing_set(self) -> None:
        with mock.patch.dict(m.os.environ, {}, clear=False):
            m.os.environ.pop("DOCKER_HOST", None)
            m.os.environ.pop("DOCKER_CONTEXT", None)
            self.assertFalse(m._remote_docker_is_active())


class TestRemoteDetail(TestCase):
    def test_names_mint_marker(self) -> None:
        with mock.patch.dict(
            m.os.environ, {"DOCKER_CONTEXT": "mint"}, clear=False
        ):
            m.os.environ.pop("DOCKER_HOST", None)
            self.assertEqual(m._remote_detail(), "mint")

    def test_names_tcp_host_marker(self) -> None:
        with mock.patch.dict(
            m.os.environ, {"DOCKER_HOST": "tcp://10.10.10.91:2376"}, clear=False
        ):
            m.os.environ.pop("DOCKER_CONTEXT", None)
            self.assertEqual(m._remote_detail(), "tcp://10.10.10.91:2376")

    def test_falls_back_to_generic_text(self) -> None:
        with mock.patch.dict(
            m.os.environ, {"DOCKER_CONTEXT": "something-else"}, clear=False
        ):
            m.os.environ.pop("DOCKER_HOST", None)
            self.assertEqual(m._remote_detail(), "remote Docker context")
