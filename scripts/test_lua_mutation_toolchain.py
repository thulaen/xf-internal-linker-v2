"""Tests for Docker-managed Lua mutation wiring."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_lua_mutmut_crate_is_workspace_member() -> None:
    workspace = read("services/speccheck/Cargo.toml")
    manifest = read("services/speccheck/crates/lua_mutmut/Cargo.toml")
    main = read("services/speccheck/crates/lua_mutmut/src/main.rs")

    assert '"crates/lua_mutmut"' in workspace
    assert 'name = "lua-mutmut"' in manifest
    assert 'features = ["luajit", "vendored"]' in manifest
    assert "mlua::Lua" in main
    assert "MutationSummary" in main


def test_lua_tool_images_install_lua_mutmut_and_luamut_alias() -> None:
    for path in ("tools/lua/Dockerfile", "tools/mutation/Dockerfile"):
        text = read(path)
        assert "crates/lua_mutmut" in text
        assert "lua-mutmut" in text
        assert "luamut" in text


def test_lua_quality_runner_uses_real_mutation_gate() -> None:
    runner = read("scripts/run-lua-quality.sh")

    assert "lua_mutation_args=(" in runner
    assert "--report reports/lua/mutation.json" in runner
    assert 'lua-mutmut "${lua_mutation_args[@]}"' in runner
    assert "MUTATION-NOT-WIRED" not in runner
    assert "luamut --version" in runner
    assert "mutation.json" in runner
