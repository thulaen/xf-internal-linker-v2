import importlib.util
import unittest
from pathlib import Path
import os
from unittest.mock import patch

_MOD_PATH = Path(__file__).resolve().parent / "run-lua-pretooluse-advisor.py"
_spec = importlib.util.spec_from_file_location("run-lua-pretooluse-advisor", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class RunLuaPretooluseAdvisorTests(unittest.TestCase):
    @patch.dict(os.environ, {"DOCKER_HOST": "tcp://1.2.3.4:2375", "DOCKER_CONTEXT": ""}, clear=True)
    def test_remote_docker_is_active_with_host(self):
        self.assertTrue(mod._remote_docker_is_active())

    @patch.dict(os.environ, {"DOCKER_HOST": "", "DOCKER_CONTEXT": "remote-context"}, clear=True)
    def test_remote_docker_is_active_with_context(self):
        self.assertTrue(mod._remote_docker_is_active())

    @patch.dict(os.environ, {"DOCKER_HOST": "", "DOCKER_CONTEXT": "desktop-linux"}, clear=True)
    def test_remote_docker_is_active_false_for_desktop_linux(self):
        self.assertFalse(mod._remote_docker_is_active())

    @patch.dict(os.environ, {"DOCKER_HOST": "ssh://user@host", "DOCKER_CONTEXT": ""}, clear=True)
    def test_remote_detail_identifies_ssh(self):
        self.assertEqual(mod._remote_detail(), "ssh://")

    @patch.dict(os.environ, {"DOCKER_HOST": "", "DOCKER_CONTEXT": "mint"}, clear=True)
    def test_remote_detail_identifies_mint(self):
        self.assertEqual(mod._remote_detail(), "mint")

if __name__ == "__main__":
    unittest.main()
