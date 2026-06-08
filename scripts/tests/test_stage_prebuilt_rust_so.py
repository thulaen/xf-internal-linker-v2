"""Tests for scripts/_stage_prebuilt_rust_so.py — the prebuilt-Rust-.so stager.

This stager takes a Rust cdylib that was built ON DELL (named `lib<name>.so`)
and places it into MSI's compiled-artifacts store + active/extensions directory
as a bare `<name>.so`, reusing ensure_compiled_artifacts' own content-addressing
functions so the kernel persists across reboots (it lands in the same manifest
record the in-container Rust build path uses) and so the stale C++ `.so` of the
same name is removed.

These tests run against a temporary fake artifact root (no Docker, no real
volume) so they pass in plain SimpleTestCase-style execution.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture()
def staging_env(tmp_path, monkeypatch):
    """Point ensure_compiled_artifacts at a temp artifact root and reload both modules."""
    artifact_root = tmp_path / "compiled"
    monkeypatch.setenv("XF_COMPILED_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setenv("XF_BACKEND_ROOT", str(tmp_path / "app"))
    monkeypatch.setenv("REPO_ROOT", str(tmp_path / "repo"))

    eca = importlib.import_module("ensure_compiled_artifacts")
    eca = importlib.reload(eca)
    stager = importlib.import_module("_stage_prebuilt_rust_so")
    stager = importlib.reload(stager)

    eca.ACTIVE_EXTENSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    return eca, stager, artifact_root


def _write_so(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_when_prebuilt_so_staged_then_bare_active_so_exists_and_store_addressed(
    staging_env, tmp_path
):
    eca, stager, artifact_root = staging_env
    lib = _write_so(tmp_path / "in" / "libanchor_self_information.so", b"RUST-KERNEL-BYTES")

    rc = stager.stage_prebuilt_rust_so(name="anchor_self_information", so_path=lib)

    assert rc == 0
    active = eca.ACTIVE_EXTENSIONS_ROOT / "anchor_self_information.so"
    assert active.exists(), "bare <name>.so must be in active/extensions"
    assert active.read_bytes() == b"RUST-KERNEL-BYTES"
    # Content-addressed into the store by the module's own hashing.
    sha = eca._file_sha256(lib)
    assert (eca.STORE_ROOT / sha).exists(), "artifact must be content-addressed into the store"


def test_when_staged_then_stale_cpython_so_is_removed(staging_env, tmp_path):
    eca, stager, artifact_root = staging_env
    stale = eca.ACTIVE_EXTENSIONS_ROOT / "anchor_self_information.cpython-312-x86_64-linux-gnu.so"
    _write_so(stale, b"OLD-CPP")
    lib = _write_so(tmp_path / "in" / "libanchor_self_information.so", b"NEW-RUST")

    stager.stage_prebuilt_rust_so(name="anchor_self_information", so_path=lib)

    assert not stale.exists(), "stale ABI-tagged C++ .so must be purged so Rust .so wins import"
    assert (eca.ACTIVE_EXTENSIONS_ROOT / "anchor_self_information.so").exists()


def test_when_staged_then_manifest_rust_record_is_added_for_persistence(staging_env, tmp_path):
    eca, stager, artifact_root = staging_env
    lib = _write_so(tmp_path / "in" / "libanchor_self_information.so", b"RUST")

    stager.stage_prebuilt_rust_so(name="anchor_self_information", so_path=lib)

    manifest = eca._load_manifest()
    artifacts = manifest["active"]["rust_extensions"]["artifacts"]
    by_module = {a["module"]: a for a in artifacts}
    assert "anchor_self_information" in by_module, "kernel must be in the manifest so it persists across reboots"
    rec = by_module["anchor_self_information"]
    assert rec["filename"] == "anchor_self_information.so"
    assert rec["active_path"] == str(eca.ACTIVE_EXTENSIONS_ROOT / "anchor_self_information.so")
    assert Path(rec["store_path"]).exists()
    # _rust_extensions_present must now report True for this entry (drives boot skip).
    assert eca._rust_extensions_present(manifest["active"]["rust_extensions"]) is True


def test_when_kernel_already_in_manifest_then_record_is_replaced_not_duplicated(
    staging_env, tmp_path
):
    eca, stager, artifact_root = staging_env
    lib1 = _write_so(tmp_path / "in" / "libl2norm.so", b"V1")
    stager.stage_prebuilt_rust_so(name="l2norm", so_path=lib1)
    lib2 = _write_so(tmp_path / "in2" / "libl2norm.so", b"V2-NEWER")
    stager.stage_prebuilt_rust_so(name="l2norm", so_path=lib2)

    manifest = eca._load_manifest()
    artifacts = manifest["active"]["rust_extensions"]["artifacts"]
    l2_records = [a for a in artifacts if a["module"] == "l2norm"]
    assert len(l2_records) == 1, "re-staging the same kernel must replace, not duplicate, the record"
    active = eca.ACTIVE_EXTENSIONS_ROOT / "l2norm.so"
    assert active.read_bytes() == b"V2-NEWER", "active .so must reflect the newest staged bytes"


def test_when_so_path_missing_then_nonzero_and_no_partial_write(staging_env, tmp_path):
    eca, stager, _ = staging_env
    missing = tmp_path / "nope" / "libfoo.so"

    rc = stager.stage_prebuilt_rust_so(name="foo", so_path=missing)

    assert rc != 0
    assert not (eca.ACTIVE_EXTENSIONS_ROOT / "foo.so").exists()


def test_main_cli_accepts_name_and_so_flags(staging_env, tmp_path):
    eca, stager, _ = staging_env
    lib = _write_so(tmp_path / "in" / "libcounting_bloom.so", b"CB")

    rc = stager.main(["--name", "counting_bloom", "--so", str(lib)])

    assert rc == 0
    assert (eca.ACTIVE_EXTENSIONS_ROOT / "counting_bloom.so").exists()
