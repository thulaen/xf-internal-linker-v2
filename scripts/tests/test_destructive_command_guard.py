"""Convention tests for scripts/destructive_command_guard.py.

BDD:
  Given a candidate shell command string
  When command_is_allowed inspects it
  Then destructive Docker volume/prune/down-v commands are blocked with the
       exact rule name, and safe commands pass — killing mutation survivors on
       the regex patterns and the block message.

Pure string logic only — no subprocess, no filesystem.
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


dcg = _load("destructive_command_guard", "destructive_command_guard.py")


class TestCommandIsAllowed(TestCase):
    def test_non_docker_command_allowed(self):
        ok, name = dcg.command_is_allowed("ls -la")
        self.assertTrue(ok)
        self.assertIsNone(name)

    def test_safe_docker_command_allowed(self):
        ok, name = dcg.command_is_allowed("docker compose up -d backend")
        self.assertTrue(ok)
        self.assertIsNone(name)

    def test_volume_rm_blocked(self):
        ok, name = dcg.command_is_allowed("docker volume rm pgdata")
        self.assertFalse(ok)
        self.assertEqual(name, "docker volume rm")

    def test_volume_prune_blocked(self):
        ok, name = dcg.command_is_allowed("docker volume prune -f")
        self.assertFalse(ok)
        self.assertEqual(name, "docker volume prune")

    def test_system_prune_blocked(self):
        ok, name = dcg.command_is_allowed("docker system prune -af")
        self.assertFalse(ok)
        self.assertEqual(name, "docker system prune")

    def test_compose_down_dash_v_blocked(self):
        ok, name = dcg.command_is_allowed("docker compose down -v")
        self.assertFalse(ok)
        self.assertEqual(name, "docker compose down -v")

    def test_compose_down_without_v_allowed(self):
        ok, name = dcg.command_is_allowed("docker compose down")
        self.assertTrue(ok)
        self.assertIsNone(name)

    def test_compose_rm_blocked(self):
        ok, name = dcg.command_is_allowed("docker compose rm worker")
        self.assertFalse(ok)
        self.assertEqual(name, "docker compose rm")


class TestBlockMessage(TestCase):
    def test_message_includes_rule_and_command(self):
        msg = dcg.block_message("docker volume rm pgdata", "docker volume rm")
        self.assertIn("BLOCKED: docker volume rm", msg)
        self.assertIn("COMMAND: docker volume rm pgdata", msg)
        self.assertIn("WHY:", msg)
        self.assertIn("UNBLOCK:", msg)

    def test_message_default_rule_when_none(self):
        msg = dcg.block_message("docker weird", None)
        self.assertIn("BLOCKED: destructive Docker command", msg)
