"""Small SSH-backed reader for Mint-hosted shard manifests and blobs."""

from __future__ import annotations

import json
import subprocess


class MintBlobStore:
    """Read distributed-test metadata from the Mint storage host."""

    def __init__(self, host: str, user: str, root: str) -> None:
        self.host = host
        self.user = user
        self.root = root.rstrip("/")

    def _ssh(self, command: str) -> subprocess.CompletedProcess[str]:
        target = f"{self.user}@{self.host}" if self.user else self.host
        return subprocess.run(
            ["ssh", target, command],
            check=False,
            text=True,
            capture_output=True,
        )

    def read_manifest(self, run_id: str) -> list[dict]:
        """Return JSON lines from the stored manifest for a run."""
        path = f"{self.root}/runs/{run_id}/manifest.jsonl"
        result = self._ssh(f"test -f {path} && cat {path}")
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def blob_exists(self, sha256: str) -> bool:
        """Return true when the content-addressed blob exists on Mint."""
        prefix = sha256[:2]
        path = f"{self.root}/blobs/sha256/{prefix}/{sha256}"
        return self._ssh(f"test -f {path}").returncode == 0
