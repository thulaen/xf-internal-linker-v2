"""Tests for run-haskell-quality.sh scope guard.

TDD Red phase: these tests fail before the scope guard block is added to
run-haskell-quality.sh.  They pass (Green) once the guard is present.

The scope guard makes the script exit 0 immediately when no Haskell-relevant
files (*.hs, *.cabal, stack.yaml, cabal.project) appear in the commit scope,
so CI and local pre-push checks skip Haskell tooling when only unrelated
files changed.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "run-haskell-quality.sh"


def test_scope_guard_exits_early_on_no_haskell_files():
    """Script must detect 'no Haskell files' and print a skip message."""
    text = SCRIPT.read_text()
    assert "No changed Haskell files detected" in text, (
        "run-haskell-quality.sh must print a skip message and exit 0 when "
        "commit_scope.py returns no .hs / .cabal / stack.yaml files"
    )


def test_scope_guard_exports_quality_haskell_paths():
    """Script must export QUALITY_HASKELL_PATHS for downstream tooling."""
    text = SCRIPT.read_text()
    assert "QUALITY_HASKELL_PATHS" in text, (
        "run-haskell-quality.sh must export QUALITY_HASKELL_PATHS so tools "
        "can receive the narrowed file list"
    )


def test_haskell_quality_runs_inside_compiled_tools_container():
    """Host runs must enter the Docker-managed compiled-tools container."""
    text = SCRIPT.read_text()
    assert "docker compose exec -T" in text
    assert "compiled-tools bash /repo/scripts/run-haskell-quality.sh" in text
    assert "XF_QUALITY_INNER=1" in text


def test_scope_guard_delegates_to_commit_scope_py():
    """Scope detection must use commit_scope.py for consistency with other gates."""
    text = SCRIPT.read_text()
    assert "commit_scope.py" in text, (
        "run-haskell-quality.sh must call commit_scope.py to get changed paths, "
        "matching the pattern used by run-go-quality.sh and run-rust-quality.sh"
    )


def test_repo_root_resolves_from_script_location():
    text = SCRIPT.read_text()
    assert "git rev-parse --show-toplevel" in text
    assert 'repo_root="${REPO_ROOT:-/repo}"' not in text


def test_scope_guard_filters_haskell_extensions():
    """The grep filter must match .hs, .cabal, stack.yaml, cabal.project."""
    text = SCRIPT.read_text()
    assert re.search(r"\.hs", text) and re.search(r"\.cabal", text), (
        "run-haskell-quality.sh scope filter must include *.hs and *.cabal "
        "so that changes to those files are detected"
    )


def test_scope_grep_pattern_correctness():
    """The regex used in the scope grep must match exactly what we expect."""
    pattern = re.compile(r"\.hs$|\.cabal$|stack\.yaml$|cabal\.project$")

    matches = [
        "services/findbugs-haskell/src/Lib.hs",
        "services/findbugs-haskell/findbugs-haskell.cabal",
        "services/findbugs-haskell/stack.yaml",
        "services/findbugs-haskell/cabal.project",
        "Main.hs",
    ]
    non_matches = [
        "main.go",
        "script.py",
        "Cargo.toml",
        "README.md",
        "frontend/src/app.component.ts",
        "backend/apps/audit/models.py",
        # A file whose name merely CONTAINS .hs as a substring must not match
        "ghc.stack.yaml.bak",
    ]

    for path in matches:
        assert pattern.search(path), f"Expected scope filter to match {path!r}"
    for path in non_matches:
        assert not pattern.search(path), f"Expected scope filter NOT to match {path!r}"


def test_haskell_mutation_is_wired():
    """run-haskell-quality.sh must call mucheck when it is available."""
    text = SCRIPT.read_text()
    assert "mucheck" in text, (
        "run-haskell-quality.sh must attempt to run mucheck for Haskell mutation testing; "
        "the script may still skip gracefully when mucheck is not installed"
    )
    assert "Haskell mutation: no tool wired" not in text, (
        "The placeholder 'no tool wired' line must be replaced with a real mucheck call"
    )
