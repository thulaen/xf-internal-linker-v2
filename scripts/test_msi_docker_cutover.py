"""Tests for the guarded MSI Docker removal cutover helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "msi_docker_cutover.py"
POWERSHELL_PATH = ROOT / "scripts" / "remove-msi-docker.ps1"


def _load_module():
    spec = importlib.util.spec_from_file_location("msi_docker_cutover", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classifies_known_msi_volumes_by_required_action() -> None:
    mod = _load_module()
    rows = mod.classify_volumes([
        "xf-internal-linker-v2_pgdata",
        "xf-internal-linker-v2_media_files",
        "xf-internal-linker-v2_grafana_data",
        "xf-internal-linker-v2_frontend_dist",
        "xf-internal-linker-v2_frontend_tool_cache",
        "xf-internal-linker-v2_redis-data",
        "mystery_customer_volume",
    ])
    actions = {row.name: row.action for row in rows}
    assert actions["xf-internal-linker-v2_pgdata"] == "must-copy"
    assert actions["xf-internal-linker-v2_media_files"] == "must-copy"
    assert actions["xf-internal-linker-v2_grafana_data"] == "must-copy"
    assert actions["xf-internal-linker-v2_frontend_dist"] == "discard"
    assert actions["xf-internal-linker-v2_frontend_tool_cache"] == "discard"
    assert actions["xf-internal-linker-v2_redis-data"] == "recreate-after-drain"
    assert actions["mystery_customer_volume"] == "manual-review"


def test_classifies_images_as_rebuild_pull_or_review() -> None:
    mod = _load_module()
    rows = mod.classify_images([
        "xf-linker-backend-runtime:latest",
        "xf-internal-linker-v2-nginx:latest",
        "grafana/grafana:latest",
        "pgvector/pgvector:pg16",
        "<none>:<none>",
        "private/manual-only:local",
    ])
    actions = {row.name: row.action for row in rows}
    assert actions["xf-linker-backend-runtime:latest"] == "rebuild-on-dell-or-mint"
    assert actions["xf-internal-linker-v2-nginx:latest"] == "rebuild-on-dell-or-mint"
    assert actions["grafana/grafana:latest"] == "pull-by-digest"
    assert actions["pgvector/pgvector:pg16"] == "pull-by-digest"
    assert actions["<none>:<none>"] == "discard"
    assert actions["private/manual-only:local"] == "manual-review"


def test_removal_proof_lists_missing_checks_until_every_gate_passes(tmp_path: Path) -> None:
    mod = _load_module()
    proof_path = tmp_path / "proof.json"
    proof_path.write_text(json.dumps({
        "database": {"verified": True},
        "media": {"verified": False},
    }), encoding="utf-8")

    ready, missing = mod.readiness_from_file(proof_path)

    assert ready is False
    assert "media verified" in missing
    assert "observability verified" in missing
    assert "remote checks verified" in missing
    assert "rollback data present" in missing
    assert "manual review complete" in missing


def test_removal_proof_passes_only_after_all_required_gates(tmp_path: Path) -> None:
    mod = _load_module()
    proof_path = tmp_path / "proof.json"
    proof_path.write_text(json.dumps({
        "database": {"verified": True},
        "media": {"verified": True},
        "observability": {"verified": True},
        "glitchtip": {"verified": True},
        "remote_checks": {"verified": True},
        "rollback": {"verified": True},
        "manual_review": {"complete": True},
    }), encoding="utf-8")

    ready, missing = mod.readiness_from_file(proof_path)

    assert ready is True
    assert missing == []


def test_verify_proof_command_reports_malformed_json(tmp_path: Path, capsys) -> None:
    mod = _load_module()
    proof_path = tmp_path / "proof.json"
    proof_path.write_text("not-json", encoding="utf-8")

    result = mod.main(["verify-proof", "--proof-file", str(proof_path)])

    out = capsys.readouterr().out
    assert result == 2
    assert "ready=false" in out
    assert "Proof file could not be read as JSON" in out


def test_powershell_removal_helper_is_locked_by_python_proof_and_phrase() -> None:
    text = POWERSHELL_PATH.read_text(encoding="utf-8")
    assert "msi_docker_cutover.py" in text
    assert "verify-proof" in text
    assert "REMOVE MSI DOCKER AFTER VERIFIED CUTOVER" in text
    assert "$Execute" in text
    forbidden = "docker " + "volume rm"
    assert forbidden not in text
