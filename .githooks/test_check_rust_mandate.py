from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import check_rust_mandate


def test_skips_when_no_speccheck_files_staged(tmp_path: Path):
    with patch.object(check_rust_mandate, "staged_paths", return_value=["README.md"]):
        assert check_rust_mandate.main(tmp_path) == 0


def test_blocks_when_required_rust_command_fails(tmp_path: Path):
    calls: list[list[str]] = []
    (tmp_path / "services" / "speccheck").mkdir(parents=True)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.returncode = 1 if any("clippy" in part for part in cmd) else 0
        result.stdout = ""
        result.stderr = "warning: clippy failed"
        return result

    with patch.object(check_rust_mandate, "staged_paths", return_value=["services/speccheck/crates/parser/src/lib.rs"]):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 2

    assert calls


def test_runs_rust_gate_inside_compiled_tools_container(tmp_path: Path):
    calls: list[list[str]] = []
    (tmp_path / "services" / "speccheck").mkdir(parents=True)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.returncode = 0
        result.stdout = (
            "TOTAL 1205 0 100.00% 82 0 100.00% 995 0 100.00% 62 0 100.00%\n"
            if any("llvm-cov" in part for part in cmd)
            else ""
        )
        result.stderr = ""
        return result

    with patch.object(check_rust_mandate, "staged_paths", return_value=["services/speccheck/crates/parser/src/lib.rs"]):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 0

    assert calls
    assert all(call[:5] == ["docker", "compose", "exec", "-T", "compiled-tools"] for call in calls)
    flattened = "\n".join(" ".join(call) for call in calls)
    assert "cargo +nightly llvm-cov --workspace --branch --ignore-filename-regex 'crates/cli/src/main.rs' --fail-under-lines 100" in flattened
    assert (
        "cargo mutants -p speccheck-detectors --jobs 4 --timeout 60 "
        "--minimum-test-timeout 30 -- --test catalog"
    ) in flattened
    assert "cargo audit -D warnings" in flattened
    assert "cargo deny check" in flattened


def test_blocks_when_rust_branch_coverage_is_below_100(tmp_path: Path):
    (tmp_path / "services" / "speccheck").mkdir(parents=True)

    def fake_run(cmd, **kwargs):
        result = Mock()
        result.returncode = 0
        command = " ".join(cmd)
        if "llvm-cov" in command:
            result.stdout = "TOTAL 1205 0 100.00% 62 1 98.39%\n"
        else:
            result.stdout = ""
        result.stderr = ""
        return result

    with patch.object(check_rust_mandate, "staged_paths", return_value=["services/speccheck/crates/parser/src/lib.rs"]):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 2
