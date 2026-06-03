"""Static contract tests for the lua-mutmut CLI."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lua_mutator_cli_contract_is_implemented() -> None:
    main = (ROOT / "services/speccheck/crates/lua_mutmut/src/main.rs").read_text(
        encoding="utf-8"
    )

    for token in (
        "--report",
        "--helper",
        "--test",
        "--version",
        "total",
        "killed",
        "survived",
        "timeout",
        "unviable",
        "score",
    ):
        assert token in main


def test_lua_mutator_has_required_initial_mutators() -> None:
    main = (ROOT / "services/speccheck/crates/lua_mutmut/src/main.rs").read_text(
        encoding="utf-8"
    )

    for token in (
        "boolean_flip",
        "comparison_flip",
        "arithmetic_flip",
        "empty_string",
        "numeric_boundary",
        "return_nil",
    ):
        assert token in main

