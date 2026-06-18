"""Tests for the Slice 20 sidecar-image proof script."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "preflight" / "test_sidecar_images.sh"


class SidecarImageProofTests(unittest.TestCase):
    def test_when_digest_missing_then_script_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sidecar-images.lock.json"
            path.write_text(
                json.dumps({"streamd": "", "startupd": "", "sidecars": ""}),
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                env={**os.environ, "XF_SIDECAR_IMAGE_LOCKFILE": str(path)},
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[SIDECAR IMAGES READY: no]", result.stdout)
