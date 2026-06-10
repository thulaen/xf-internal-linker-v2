import importlib.util
import os
import sys
from pathlib import Path
from unittest import TestCase
from unittest import mock

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

advisor = _load()


class TestRunLuaPreToolUseAdvisor(TestCase):
    @mock.patch.dict(os.environ, {"DOCKER_HOST": "tcp://192.168.0.91:2376"}, clear=True)
    def test_remote_docker_is_active_docker_host_set(self):
        self.assertTrue(advisor._remote_docker_is_active())

    @mock.patch.dict(os.environ, {"DOCKER_CONTEXT": "mint"}, clear=True)
    def test_remote_docker_is_active_non_desktop_context(self):
        self.assertTrue(advisor._remote_docker_is_active())

    @mock.patch.dict(os.environ, {"DOCKER_CONTEXT": "desktop-linux"}, clear=True)
    def test_remote_docker_is_active_desktop_linux(self):
        self.assertFalse(advisor._remote_docker_is_active())

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_remote_docker_is_active_nothing_set(self):
        self.assertFalse(advisor._remote_docker_is_active())

    @mock.patch.dict(os.environ, {"DOCKER_HOST": "tcp://192.168.0.91:2376"}, clear=True)
    def test_remote_detail_matching_marker(self):
        self.assertEqual(advisor._remote_detail(), "tcp://192.168.0.91:2376")

    @mock.patch.dict(os.environ, {"DOCKER_CONTEXT": "mint"}, clear=True)
    def test_remote_detail_another_matching_marker(self):
        self.assertEqual(advisor._remote_detail(), "mint")

    @mock.patch.dict(os.environ, {"DOCKER_CONTEXT": "unknown-remote"}, clear=True)
    def test_remote_detail_generic_text(self):
        self.assertEqual(advisor._remote_detail(), "remote Docker context")
