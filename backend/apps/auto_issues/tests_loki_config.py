"""Config tests for Loki log retention and replay handling."""

from pathlib import Path
import os

import yaml
from django.test import SimpleTestCase


def _repo_root() -> Path:
    candidates = [Path(os.environ.get("REPO_ROOT", "")), *Path(__file__).resolve().parents]
    for candidate in candidates:
        if candidate and (candidate / "loki-config.yaml").exists():
            return candidate
    raise FileNotFoundError("Could not find loki-config.yaml")


class LokiConfigTests(SimpleTestCase):
    def test_old_sample_window_matches_retention(self) -> None:
        config = yaml.safe_load((_repo_root() / "loki-config.yaml").read_text())
        limits = config["limits_config"]

        self.assertTrue(limits["reject_old_samples"])
        self.assertEqual(limits["reject_old_samples_max_age"], limits["retention_period"])
