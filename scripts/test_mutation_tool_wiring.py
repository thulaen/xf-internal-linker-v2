"""Tests for mutation tool wiring across local and remote runners."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_no_repo_owned_mutmut_command_uses_removed_paths_to_mutate_flag() -> None:
    offenders: list[str] = []
    removed_flag = "--paths" + "-to-mutate"
    paths = [
        *ROOT.joinpath("scripts").glob("*"),
        *ROOT.joinpath(".github", "workflows").glob("*"),
    ]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if removed_flag in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_backend_mutation_image_pins_multicore_mutmut() -> None:
    text = _read("backend/Dockerfile")

    assert "mutmut==3.5.0" in text
    assert "mutmut==2.5.1" not in text


def test_compiled_mutation_image_requires_cargo_mutants() -> None:
    dockerfile = _read("tools/mutation/Dockerfile")
    compose = _read("docker-compose.yml")

    assert "cargo mutants --version" in dockerfile
    assert "command -v cargo-mutants" in compose


def test_compiled_mutation_image_installs_pinned_cargo_nextest() -> None:
    """The quality stage must install cargo-nextest from the prebuilt
    x86_64-unknown-linux-gnu release tarball at a pinned version (faster and
    more reproducible than `cargo install cargo-nextest`)."""
    text = _read("tools/mutation/Dockerfile")

    assert re.search(r"NEXTEST_VERSION=\d+\.\d+\.\d+", text), (
        "tools/mutation/Dockerfile must pin a cargo-nextest version"
    )
    assert "cargo-nextest" in text
    assert "x86_64-unknown-linux-gnu" in text
    assert "cargo install cargo-nextest" not in text


def test_compiled_mutation_image_installs_mold_linker_with_cargo_config() -> None:
    """mold + clang must be installed and selected through an image-level
    cargo config so the repo's own .cargo stays untouched (Dell-only by
    construction)."""
    text = _read("tools/mutation/Dockerfile")

    assert re.search(r"apt-get install[^&]*\bmold\b", text), (
        "tools/mutation/Dockerfile must apt-get install mold"
    )
    assert re.search(r"apt-get install[^&]*\bclang\b", text), (
        "tools/mutation/Dockerfile must apt-get install clang (mold driver)"
    )
    assert "[target.x86_64-unknown-linux-gnu]" in text
    assert 'linker = "clang"' in text
    assert "link-arg=-fuse-ld=mold" in text


def test_compiled_mutation_image_installs_pinned_sccache() -> None:
    """sccache must come from the pinned prebuilt release binary; the runtime
    wrapper env (RUSTC_WRAPPER) is set by the runner scripts, not the image."""
    text = _read("tools/mutation/Dockerfile")

    assert re.search(r"SCCACHE_VERSION=\d+\.\d+\.\d+", text), (
        "tools/mutation/Dockerfile must pin an sccache version"
    )
    assert "sccache" in text
    assert "cargo install sccache" not in text


def test_rust_runners_persist_sccache_on_named_dell_volume() -> None:
    """Both Rust runner scripts must mount the xf_sccache named volume and
    point rustc at it so compile caches survive the per-sync tree wipe."""
    for path in (
        "tools/quality/internal/run-rust-quality.sh",
        "tools/quality/internal/run-rust-mutation.sh",
    ):
        text = _read(path)
        assert "-v xf_sccache:/sccache" in text, f"{path} must mount xf_sccache"
        assert "RUSTC_WRAPPER=sccache" in text, f"{path} must set RUSTC_WRAPPER"
        assert "SCCACHE_DIR=/sccache" in text, f"{path} must set SCCACHE_DIR"


def test_python_mutation_runner_is_dell_only() -> None:
    """Pre-push Python mutation runs on Dell only — no local container, no
    turbo delegate, with the >=90% kill gate and content-hash pair caching."""
    text = _read("tools/quality/internal/run-python-mutation.sh")

    assert 'PYTHON_MUTATION_DOCKER_CONTEXT="${PYTHON_MUTATION_DOCKER_CONTEXT:-dell}"' in text
    assert 'scripts/remote_docker.py --host "$PYTHON_MUTATION_DOCKER_CONTEXT"' in text
    assert "xf_python_mutation_repo" in text
    assert "xf-linker-backend-mutation-tools" in text
    assert ">= 90.0" in text
    assert "filter-pairs --tool mutmut" in text
    assert "record-pairs --tool mutmut" in text
    assert "[tool.mutmut]" in text
    assert "paths_to_mutate" in text
    assert "mutmut run --max-children" in text
    assert "XF_TURBO_MUTATION" not in text
    assert "backend-quality" not in text
    # The Windows-local mutation runner is gone for good.
    assert not (ROOT / "scripts" / "run-windows-mutation.ps1").exists()


def test_ci_python_mutation_uses_bazel() -> None:
    text = _read(".github/workflows/ci.yml")

    assert "python scripts/bazel_default.py run //tools/quality:mutation" in text
    assert "mutmut run --max-children" not in text


def test_scoped_mutation_workflow_uses_bazel() -> None:
    text = _read(".github/workflows/scoped-mutation.yml")

    assert "python scripts/bazel_default.py run //tools/quality:mutation" in text
    assert "mutmut run --max-children" not in text


def test_other_mutation_wrappers_expose_expected_tool_contracts() -> None:
    # Only the two surviving mutation wrappers: Angular (TypeScript/Stryker)
    # and Rust (cargo-mutants). C++, Go, and Haskell removed per ADR 0007.
    checks = {
        "tools/quality/internal/run-angular-mutation.sh": (
            "npx stryker run",
        ),
        "tools/quality/internal/run-rust-mutation.sh": (
            "cargo mutants",
            "cargo-mutants is required for Rust mutation",
            "--in-diff",
        ),
    }

    for path, expected_parts in checks.items():
        text = _read(path)
        for expected in expected_parts:
            assert expected in text, f"{path} missing {expected!r}"


def test_rust_mutation_config_lists_both_workspaces() -> None:
    """config/mutation-routing.json rust block must cover /repo/rust too."""
    import json

    config = json.loads(_read("config/mutation-routing.json"))
    rust = config["languages"]["rust"]
    # A `workspaces` list (plural) is the new shape that lets cargo-mutants run
    # across every Rust workspace. Both the speccheck service and the new
    # /repo/rust kernels workspace must appear.
    workspaces = rust.get("workspaces")
    assert isinstance(workspaces, list), (
        "rust block must declare a `workspaces` list so cargo-mutants covers "
        "more than one Rust workspace"
    )
    assert "/repo/services/speccheck" in workspaces
    assert "/repo/rust" in workspaces
    # The kill-rate gate must stay at 0.90 (unchanged).
    assert config["kill_rate_gates"]["rust"] == 0.90


def test_rust_quality_syncs_rust_workspace_to_dell() -> None:
    """run-rust-quality.sh must ship rust/ to the Dell volume before running."""
    text = _read("tools/quality/internal/run-rust-quality.sh")
    # The host-side re-exec tars the source roots into the Dell volume, and the
    # remote cleanup must remove the old tree before re-extracting, otherwise the
    # inner run-rust-quality.sh finds no /repo/rust workspace on Dell.
    assert "tar -cf -" in text
    assert re.search(r"sync_roots=\([^)]*\brust\b", text), (
        "run-rust-quality.sh sync_roots must include rust/ so the "
        "/repo/rust workspace exists on the Dell compute shard"
    )
    assert "/repo/rust" in text, (
        "run-rust-quality.sh remote cleanup (rm -rf) must remove "
        "/repo/rust before re-extracting the synced tree"
    )
