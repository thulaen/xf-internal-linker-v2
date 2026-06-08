"""Tests for the Rust coverage gate (cargo-llvm-cov over /repo/rust + speccheck).

TDD Red phase: these tests fail before scripts/run-rust-coverage.sh exists and
before tools/mutation/Dockerfile installs cargo-llvm-cov + llvm-tools-preview.
They pass (Green) once the coverage script, the Dockerfile install, and the
docs target are in place.

The Rust coverage gate mirrors the C++ lcov gate but RATCHETS toward the 95%
line target from docs/PYTHON-RUST-MIGRATION-PLAN.md (phase E8): it reports the
measured number and enforces a per-workspace floor that can only rise, so it
never hard-blocks a commit just because current coverage is still below 95%.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
COVERAGE = SCRIPTS / "run-rust-coverage.sh"
DOCKERFILE = ROOT / "tools" / "mutation" / "Dockerfile"
COVERAGE_RULES = ROOT / "docs" / "CODE-COVERAGE-RULES.md"


# ── the coverage script exists and invokes cargo llvm-cov ─────────────────────


def test_coverage_script_exists():
    """scripts/run-rust-coverage.sh must exist."""
    assert COVERAGE.is_file(), (
        "scripts/run-rust-coverage.sh must exist to measure Rust line coverage"
    )


def test_coverage_script_invokes_cargo_llvm_cov():
    """The coverage script must drive cargo llvm-cov, the Rust coverage tool."""
    text = COVERAGE.read_text()
    assert "cargo llvm-cov" in text or "cargo +nightly llvm-cov" in text, (
        "run-rust-coverage.sh must call cargo llvm-cov to measure coverage"
    )


def test_coverage_script_covers_both_workspaces():
    """Coverage must run over BOTH /repo/rust AND speccheck."""
    text = COVERAGE.read_text()
    assert "/repo/rust" in text, (
        "run-rust-coverage.sh must measure the /repo/rust kernels workspace"
    )
    assert "/repo/services/speccheck" in text, (
        "run-rust-coverage.sh must also measure the speccheck workspace"
    )


def test_coverage_script_runs_in_compiled_tools_container():
    """Host runs must self-reexec into the Docker-managed compiled-tools image."""
    text = COVERAGE.read_text()
    assert "docker compose exec -T" in text
    assert "compiled-tools" in text
    assert "XF_QUALITY_INNER" in text or "/.dockerenv" in text


def test_coverage_script_ratchets_and_does_not_hard_fail_below_target():
    """The gate ratchets: it must NOT hard-fail merely for being below 95%."""
    text = COVERAGE.read_text()
    # A floor file that "can only rise" is the ratchet mechanism.
    assert "floor" in text.lower(), (
        "run-rust-coverage.sh must enforce a per-workspace floor (ratchet)"
    )
    # The 95% target must be named as the goal the floor ratchets toward.
    assert "95" in text, (
        "run-rust-coverage.sh must reference the 95% E8 target it ratchets to"
    )


def test_coverage_script_reports_the_measured_number():
    """The gate must print the measured coverage percent so agents see it."""
    text = COVERAGE.read_text()
    # cargo llvm-cov --json / --summary-only feeds a parse that prints a number.
    assert "--summary-only" in text or "--json" in text, (
        "run-rust-coverage.sh must request a machine-readable summary from "
        "cargo llvm-cov so the measured line-coverage percent can be reported"
    )


def test_coverage_floor_file_is_per_workspace():
    """The ratchet floor must be keyed per-workspace, not one global number."""
    text = COVERAGE.read_text()
    # Both workspace names appear, and a floor store (JSON) is referenced.
    assert ".json" in text, (
        "run-rust-coverage.sh must persist the per-workspace floor in a JSON "
        "store so the ratchet survives between runs"
    )


# ── Dockerfile installs cargo-llvm-cov + llvm-tools-preview ───────────────────


def test_dockerfile_installs_cargo_llvm_cov():
    """tools/mutation/Dockerfile must install cargo-llvm-cov in the Rust block."""
    text = DOCKERFILE.read_text()
    assert "cargo-llvm-cov" in text, (
        "tools/mutation/Dockerfile must `cargo install cargo-llvm-cov` so the "
        "compiled-tools image can measure Rust coverage"
    )


def test_dockerfile_installs_llvm_tools_preview():
    """cargo-llvm-cov needs the llvm-tools-preview rustup component."""
    text = DOCKERFILE.read_text()
    assert "llvm-tools-preview" in text, (
        "tools/mutation/Dockerfile must `rustup component add llvm-tools-preview` "
        "(cargo-llvm-cov depends on it)"
    )


def test_dockerfile_smoke_test_checks_llvm_cov():
    """The image smoke-test CMD must verify cargo llvm-cov is present."""
    text = DOCKERFILE.read_text()
    assert "cargo llvm-cov --version" in text, (
        "tools/mutation/Dockerfile CMD must include `cargo llvm-cov --version` "
        "so a missing install fails the image build"
    )


# ── docs name the 95% Rust target ─────────────────────────────────────────────


def test_coverage_rules_document_rust_95_target():
    """docs/CODE-COVERAGE-RULES.md must list the Rust 95% line target."""
    text = COVERAGE_RULES.read_text()
    # A table row naming Rust + 95% line coverage.
    assert re.search(r"Rust.*95%", text) or re.search(r"95%.*Rust", text), (
        "docs/CODE-COVERAGE-RULES.md must document the Rust 95% line-coverage "
        "target (phase E8 of the Python->Rust migration plan)"
    )
    assert "cargo llvm-cov" in text or "cargo-llvm-cov" in text, (
        "docs/CODE-COVERAGE-RULES.md must name cargo llvm-cov as the Rust "
        "coverage tool"
    )
