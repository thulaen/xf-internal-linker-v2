"""
SHA-256 content-addressed blob store client for the Mint artifact host.

Upload protocol:
  1. Compute SHA-256 of the local artifact.
  2. Ask Mint via SSH whether the blob already exists.
  3. If new: SCP to temp-upload, SSH rename into blob-store (atomic).
  4. Append a JSONL manifest entry to runs/<run_id>/manifest.json.
  5. Return the manifest entry dict.

References:
  SHA-256: RFC 6234 (https://datatracker.ietf.org/doc/html/rfc6234)
  Content addressing: https://bazel.build/remote/rbe
  Hamilton apportionment: Balinski & Young 1982 (ISBN 978-0815710103)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MINT_ROOT_DEFAULT = "/srv/xf"
BLOB_STORE_SUBDIR = "artifacts/blob-store/sha256"
TEMP_UPLOAD_SUBDIR = "temp-upload"
RUNS_SUBDIR = "artifacts/runs"


def compute_sha256(path: str | Path) -> str:
    """Return the lowercase hex SHA-256 digest of a local file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class _SSHTransport:
    """Default SSH/SCP transport backed by subprocess."""

    def __init__(self, host: str, user: str) -> None:
        self.host = host
        self.user = user
        self._target = f"{user}@{host}"

    def blob_exists(self, blob_path: str) -> bool:
        result = subprocess.run(
            ["ssh", self._target, f"test -f {blob_path}"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0

    def upload_file(self, local_path: str, remote_path: str) -> None:
        result = subprocess.run(
            ["scp", local_path, f"{self._target}:{remote_path}"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"SCP failed: {local_path!r} → {remote_path!r}\n{result.stderr}"
            )

    def atomic_move(self, src: str, dst: str) -> None:
        dst_dir = dst.rsplit("/", 1)[0]
        result = subprocess.run(
            ["ssh", self._target, f"mkdir -p {dst_dir} && mv {src} {dst}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"SSH mv failed: {src!r} → {dst!r}\n{result.stderr}"
            )

    def append_line(self, remote_path: str, line: str) -> None:
        # Write JSON line to local temp, SCP it, then cat-append on Mint and rm.
        remote_dir = remote_path.rsplit("/", 1)[0]
        tmp_name = f"{uuid.uuid4().hex}.appendtmp"
        tmp_remote = f"/{TEMP_UPLOAD_SUBDIR}/{tmp_name}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".appendtmp", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(line + "\n")
            local_tmp = tf.name
        try:
            self.upload_file(local_tmp, tmp_remote)
        finally:
            os.unlink(local_tmp)
        cmd = (
            f"mkdir -p {remote_dir} && "
            f"cat {tmp_remote} >> {remote_path} && "
            f"rm {tmp_remote}"
        )
        result = subprocess.run(
            ["ssh", self._target, cmd],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Manifest append failed for {remote_path!r}\n{result.stderr}"
            )

    def read_lines(self, remote_path: str) -> list[str]:
        result = subprocess.run(
            ["ssh", self._target, f"cat {remote_path} 2>/dev/null || true"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"SSH cat failed for {remote_path!r}\n{result.stderr}"
            )
        return [ln for ln in result.stdout.splitlines() if ln.strip()]

    def list_blobs(self, blob_store_root: str) -> list[str]:
        result = subprocess.run(
            [
                "ssh",
                self._target,
                f"find {blob_store_root} -type f -maxdepth 3 2>/dev/null || true",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]

    def delete_blob(self, blob_path: str) -> None:
        result = subprocess.run(
            ["ssh", self._target, f"rm -f {blob_path}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"SSH rm failed: {blob_path!r}\n{result.stderr}"
            )


class MintBlobStore:
    """SHA-256 content-addressed blob store on the Mint host.

    Args:
        mint_host:  Hostname or IP of the Mint machine.
        ssh_user:   SSH username for Mint access.
        mint_root:  Root directory on Mint (default /srv/xf).
        transport:  Injectable transport for testing. If None, uses SSH/SCP.
    """

    def __init__(
        self,
        mint_host: str,
        ssh_user: str,
        mint_root: str = MINT_ROOT_DEFAULT,
        *,
        transport: Any = None,
    ) -> None:
        self.mint_host = mint_host
        self.ssh_user = ssh_user
        self.mint_root = mint_root.rstrip("/")
        self._t = transport or _SSHTransport(mint_host, ssh_user)

    # ── Path helpers ──────────────────────────────────────────────────────

    def blob_path(self, sha256: str) -> str:
        """Canonical blob path on Mint: .../sha256/<first2>/<full_sha256>."""
        return f"{self.mint_root}/{BLOB_STORE_SUBDIR}/{sha256[:2]}/{sha256}"

    def temp_path(self, sha256: str) -> str:
        """Staging path before atomic rename: .../temp-upload/<sha256>.tmp."""
        return f"{self.mint_root}/{TEMP_UPLOAD_SUBDIR}/{sha256}.tmp"

    def manifest_path(self, run_id: str) -> str:
        """JSONL manifest path for a run: .../runs/<run_id>/manifest.json."""
        return f"{self.mint_root}/{RUNS_SUBDIR}/{run_id}/manifest.json"

    # ── Core operations ───────────────────────────────────────────────────

    def blob_exists(self, sha256: str) -> bool:
        """Return True if the blob already exists on Mint."""
        return self._t.blob_exists(self.blob_path(sha256))

    def upload(
        self,
        local_path: str | Path,
        *,
        run_id: str,
        shard_id: str,
        tool: str,
        logical_path: str,
        worker: str = "windows",
        required_for_merge: bool = True,
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload a local artifact to Mint and append a manifest entry.

        Deduplicates: if the SHA-256 blob already exists on Mint, the SCP
        and atomic rename are skipped — but a new manifest entry is always
        appended so two shards that produced identical bytes are both tracked.

        Returns the manifest entry dict.

        Raises RuntimeError if SCP or SSH mv fails (caller fails the shard).
        """
        local_path = str(local_path)
        sha256 = compute_sha256(local_path)
        size_bytes = os.path.getsize(local_path)

        if not self.blob_exists(sha256):
            tmp = self.temp_path(sha256)
            self._t.upload_file(local_path, tmp)
            blob = self.blob_path(sha256)
            self._t.atomic_move(tmp, blob)

        entry: dict[str, Any] = {
            "run_id": run_id,
            "worker": worker,
            "shard_id": shard_id,
            "tool": tool,
            "logical_path": logical_path,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "media_type": media_type,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "required_for_merge": required_for_merge,
        }
        manifest = self.manifest_path(run_id)
        self._t.append_line(manifest, json.dumps(entry, separators=(",", ":")))
        return entry

    def read_manifest(self, run_id: str) -> list[dict[str, Any]]:
        """Read all manifest entries for a run as a list of dicts."""
        lines = self._t.read_lines(self.manifest_path(run_id))
        return [json.loads(ln) for ln in lines if ln.strip()]
