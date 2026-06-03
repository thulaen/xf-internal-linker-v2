"""Tests for Mint test/cache artifact retention and dedupe."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import mint_gc
from mint_blob_store import MintBlobStore


class FakeTransport:
    def __init__(self) -> None:
        self.blobs: set[str] = set()
        self.uploads: list[tuple[str, str]] = []
        self.manifest_lines: list[str] = []

    def blob_exists(self, blob_path: str) -> bool:
        return blob_path in self.blobs

    def upload_file(self, local_path: str, remote_path: str) -> None:
        self.uploads.append((local_path, remote_path))

    def atomic_move(self, src: str, dst: str) -> None:
        self.blobs.add(dst)

    def append_line(self, remote_path: str, line: str) -> None:
        self.manifest_lines.append(line)


def test_mint_gc_defaults_to_fourteen_day_test_cache_retention() -> None:
    assert mint_gc.DEFAULT_RETENTION_DAYS == 14
    assert "--grace-period-days" in Path(mint_gc.__file__).read_text(encoding="utf-8")
    assert "default=DEFAULT_RETENTION_DAYS" in Path(mint_gc.__file__).read_text(encoding="utf-8")


def test_windows_mint_spec_names_fourteen_day_deduped_cache_policy() -> None:
    spec = (Path(__file__).resolve().parents[1] / "docs" / "specs" / "fr-windows-mint-compute-split.md").read_text(encoding="utf-8")

    assert "14-day retention policy" in spec
    assert "dedupes them by" in spec
    assert "SHA-256" in spec


def test_retained_sha256s_ignore_expired_test_cache_manifests(tmp_path: Path) -> None:
    now = datetime(2026, 5, 28, tzinfo=UTC)
    fresh_sha = "a" * 64
    expired_sha = "b" * 64
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        "\n".join(
            [
                json.dumps({"sha256": fresh_sha, "created_at": (now - timedelta(days=13)).strftime("%Y-%m-%dT%H:%M:%SZ")}),
                json.dumps({"sha256": expired_sha, "created_at": (now - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")}),
            ]
        ),
        encoding="utf-8",
    )

    retained = mint_gc.collect_retained_sha256s([manifest], retention_days=14, now=now)

    assert retained == {fresh_sha}
    assert mint_gc.collect_garbage(
        [f"/srv/xf/artifacts/blob-store/sha256/bb/{expired_sha}"],
        retained_sha256s=retained,
        grace_period_days=0,
    ) == [f"/srv/xf/artifacts/blob-store/sha256/bb/{expired_sha}"]


def test_blob_store_dedupes_identical_test_cache_bytes(tmp_path: Path) -> None:
    artifact_one = tmp_path / "one.log"
    artifact_two = tmp_path / "two.log"
    artifact_one.write_text("same test output\n", encoding="utf-8")
    artifact_two.write_text("same test output\n", encoding="utf-8")
    transport = FakeTransport()
    store = MintBlobStore("mint", "xf", transport=transport)

    first = store.upload(
        artifact_one,
        run_id="run-1",
        shard_id="windows-0",
        tool="pytest",
        logical_path="test-cache/pytest/one.log",
    )
    second = store.upload(
        artifact_two,
        run_id="run-2",
        shard_id="mint-0",
        tool="pytest",
        logical_path="test-cache/pytest/two.log",
    )

    assert first["sha256"] == second["sha256"]
    assert len(transport.uploads) == 1
    assert len(transport.manifest_lines) == 2
