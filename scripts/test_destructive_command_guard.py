import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "destructive_command_guard.py"
_spec = importlib.util.spec_from_file_location("destructive_command_guard", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class DestructiveCommandGuardTests(unittest.TestCase):
    def test_normalize_command_removes_extra_spaces(self):
        self.assertEqual(mod._normalize_command("docker   volume   rm"), "docker volume rm")
        self.assertEqual(mod._normalize_command(" docker  system prune "), "docker system prune")

    def test_command_is_allowed_allows_safe_commands(self):
        allowed, rule = mod.command_is_allowed("docker ps")
        self.assertTrue(allowed)
        self.assertIsNone(rule)

        allowed, rule = mod.command_is_allowed("docker compose build")
        self.assertTrue(allowed)
        self.assertIsNone(rule)

    def test_command_is_allowed_blocks_destructive_commands(self):
        allowed, rule = mod.command_is_allowed("docker volume rm my-vol")
        self.assertFalse(allowed)
        self.assertEqual(rule, "docker volume rm")

        allowed, rule = mod.command_is_allowed("docker compose down -v")
        self.assertFalse(allowed)
        self.assertEqual(rule, "docker compose down -v")
        
        allowed, rule = mod.command_is_allowed("docker compose rm -f")
        self.assertFalse(allowed)
        self.assertEqual(rule, "docker compose rm")

    def test_block_message_formats_correctly(self):
        msg = mod.block_message("docker volume rm", "docker volume rm")
        self.assertIn("BLOCKED: docker volume rm", msg)
        self.assertIn("COMMAND: docker volume rm", msg)

if __name__ == "__main__":
    unittest.main()
