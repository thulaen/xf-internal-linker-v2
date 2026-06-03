"""Tests for shared AWS cache bucket lifecycle configuration."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "aws-cache-buckets.json"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cache_bucket_config_is_deduped_and_uses_fourteen_day_retention() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    names = [bucket["name"] for bucket in config["buckets"]]

    assert config["retention_days"] == 14
    assert len(names) == len(set(names))
    assert names == [
        "xf-internal-linker-sccache",
        "xf-internal-linker-buildkit-cache",
    ]


def test_cache_retention_script_reads_shared_config_instead_of_hardcoding_buckets() -> None:
    script = _read("scripts/apply-cache-retention.ps1")

    assert "aws-cache-buckets.json" in script
    assert "ConvertFrom-Json" in script
    assert "put-bucket-lifecycle-configuration" in script
    assert "xf-internal-linker-sccache" not in script
    assert "xf-internal-linker-buildkit-cache" not in script
    assert "retention_days" in script


def test_cache_docs_point_at_the_shared_config_and_fourteen_day_policy() -> None:
    for path in ("docs/SCCACHE-S3-SETUP.md", "docs/DOCKER-BUILDKIT-S3-SETUP.md"):
        text = _read(path)
        assert "config/aws-cache-buckets.json" in text
        assert "14 days" in text
        assert "scripts/apply-cache-retention.ps1" in text
