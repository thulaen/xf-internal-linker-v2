"""Tests for the LuaJIT 2.1 test-tool wiring."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
ADVISOR_COMMAND = "python scripts/run-lua-pretooluse-advisor.py"


LUA_CATEGORIES = {
    "content": (
        "apps/content/format_filters/xf_post_format.lua",
        "apps/content/format_filters/tests/xf_post_format_spec.lua",
    ),
    "anchors": (
        "apps/suggestions/anchor_shapes/generic_rewriter.lua",
        "apps/suggestions/anchor_shapes/tests/generic_rewriter_spec.lua",
    ),
    "openresty": (
        "frontend/nginx-lua/json_schema_validator.lua",
        "frontend/nginx-lua/tests/json_schema_validator_spec.lua",
    ),
    "lefthook": (
        ".githooks/lua/queue_fetcher.lua",
        ".githooks/lua/tests/queue_fetcher_spec.lua",
    ),
    "advisor": (
        "apps/governance/lua_runtime/advisors/workflow_state_reminder.lua",
        "apps/governance/lua_runtime/advisors/tests/workflow_state_reminder_spec.lua",
    ),
    "redis": (
        "apps/governance/redis_scripts/autoissue_dedup.lua",
        "apps/governance/redis_scripts/tests/autoissue_dedup_spec.lua",
    ),
}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _contains_command(value: object, expected: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_command(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_command(item, expected) for item in value)
    return isinstance(value, str) and expected in value


def test_lua_tool_versions_are_pinned() -> None:
    versions = _read(".tool-versions")
    for expected in (
        "luajit 2.1.0-beta3",
        "luarocks 3.11.1",
        "busted 2.2.0-1",
        "luacheck 1.2.0-1",
        "luacov 0.16.0-1",
        "luacov-cobertura 0.2-1",
        "lua-quickcheck 0.2-4",
    ):
        assert expected in versions


def test_docker_images_install_pinned_lua_tools() -> None:
    backend = _read("backend/Dockerfile")
    mutation = _read("tools/mutation/Dockerfile")
    lua_tools = _read("tools/lua/Dockerfile")
    nginx = _read("nginx/Dockerfile")
    for text in (backend, mutation, lua_tools):
        assert "luajit" in text
        assert "luarocks" in text
        assert "busted" in text
        assert "luacheck" in text
        assert "luacov" in text
    assert "cargo install --path /tmp/speccheck/crates/lua_fastcheck --locked" in mutation
    assert "cargo install --path /tmp/speccheck/crates/lua_fastcheck --locked" in lua_tools
    assert "cargo install --path /tmp/speccheck/crates/lua_mutmut --locked" in mutation
    assert "cargo install --path /tmp/speccheck/crates/lua_mutmut --locked" in lua_tools
    assert "command -v lua-fastcheck >/dev/null" in mutation
    assert "command -v lua-fastcheck >/dev/null" in lua_tools
    assert "lua-mutmut --version" in mutation
    assert "lua-mutmut --version" in lua_tools
    assert "openresty/openresty" in nginx
    assert "alpine" in nginx


def test_lua_categories_have_first_script_and_busted_spec() -> None:
    for source_path, spec_path in LUA_CATEGORIES.values():
        source = _read(source_path)
        spec = _read(spec_path)
        assert "return" in source
        assert "describe(" in spec
        assert "it(" in spec
        assert "io." not in source
        assert "os." not in source
        assert "debug." not in source
        assert "require(" not in source


def test_sandbox_loader_and_test_harness_enforce_forbidden_libraries() -> None:
    loader = _read("apps/governance/lua_runtime/sandbox_loader.py")
    harness = _read("apps/governance/lua_runtime/test_harness.py")
    for forbidden in ("io", "os", "debug", "require"):
        assert forbidden in loader
        assert forbidden in harness
    assert "LuaSandboxViolationError" in loader
    assert "mock_capability" in harness
    assert "advisor_mode" in harness


def test_lua_quality_runner_uses_adaptive_workers_and_all_tools() -> None:
    runner = _read("scripts/run-lua-quality.sh")
    assert ". scripts/_quality_concurrency.sh" in runner
    assert "quality_cores busted" in runner
    assert "scripts/commit_scope.py paths --mode" in runner
    assert "XF_LUA_QUALITY_SCOPE" in runner
    assert "XF_LUA_QUALITY_IN_CONTAINER" in runner
    assert "quality_docker_compose_run lua-quality lua-quality-tools" in runner
    assert "ensure_local_control_plane_docker" in runner
    assert "DOCKER_CONTEXT=desktop-linux" in runner
    assert "DOCKER_HOST" in runner
    assert "tcp://10.10.10.91:2376" in runner
    assert "tcp://192.168.0.91:2376" in runner
    assert "ssh://" in runner
    assert "mint" in runner
    assert "dell" in runner
    assert "--full" in runner
    assert "lua-fastcheck" in runner
    assert "command -v lua-fastcheck" in runner
    assert "Python fallback" not in runner
    assert "check-lua-sandbox.py" not in runner
    assert 'busted --helper scripts/lua_busted_helper.lua "${test_files[@]}"' in runner
    assert 'busted --coverage --helper scripts/lua_busted_helper.lua "${test_files[@]}"' in runner
    assert "busted 2.2.0 has no --jobs flag" in runner
    assert "luacheck --config .luacheckrc" in runner
    assert "luajit -bl" in runner
    assert "luacov-cobertura" in runner
    assert "lua_mutation_args=(" in runner
    assert "--report reports/lua/mutation.json" in runner
    assert 'lua-mutmut "${lua_mutation_args[@]}"' in runner
    assert "MUTATION-NOT-WIRED: language=lua" not in runner


def test_agent_rules_lock_lua_and_redis_to_windows_local_control_plane() -> None:
    required = (
        "Local control plane stays on Windows Docker Desktop",
        "Lua advisor/runtime/tooling",
        "Redis",
        "session lookup",
        "desktop-linux",
        "Mint",
        "Dell",
        "CodeBuild",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
    )
    for path in ("AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md", "AI-CONTEXT.md"):
        text = _read(path)
        for marker in required:
            assert marker in text, f"{path} missing {marker}"


def test_live_agent_configs_wire_lua_pretooluse_advisor() -> None:
    claude = json.loads(_read(".claude/settings.json"))
    assert _contains_command(claude["hooks"]["PreToolUse"], f"{ADVISOR_COMMAND} --agent claude")

    codex = tomllib.loads(_read(".codex/config.toml"))
    assert _contains_command(codex["hooks"]["pre_tool_use"], f"{ADVISOR_COMMAND} --agent codex")

    gemini = json.loads(_read(".gemini/extensions.json"))
    assert _contains_command(gemini, f"{ADVISOR_COMMAND} --agent gemini")


def test_lua_pretooluse_launcher_runs_advisor_on_desktop_context() -> None:
    launcher = _read("scripts/run-lua-pretooluse-advisor.py")
    assert "workflow_state_reminder.lua" in launcher
    assert "LUA_DRIVER" in launcher
    assert "desktop-linux" in launcher
    assert "DOCKER_CONTEXT" in launcher
    assert "DOCKER_HOST" in launcher
    assert "XF_LUA_PAYLOAD_FILE" in launcher
    assert "tool_call = { read = function() return payload end }" in launcher
    assert "_prune_stale_payload_files" in launcher
    assert "lua-advisor-payload-*.json" in launcher
    assert "STALE_PAYLOAD_SECONDS = 600" in launcher
    assert "lua-quality-tools" in launcher
    assert "LuaAdvisorUnavailableError" in launcher
    assert "ADVISOR_TIMEOUT_SECONDS = 15" in launcher
    assert "_read_payload" in launcher
    assert 'process.communicate("", timeout=ADVISOR_TIMEOUT_SECONDS)' in launcher
    assert "return 0" in launcher
    assert not (ROOT / "scripts/lua_pretooluse_driver.lua").exists()


def test_mlua_fastcheck_crate_is_wired_into_rust_workspace() -> None:
    workspace = _read("services/speccheck/Cargo.toml")
    manifest = _read("services/speccheck/crates/lua_fastcheck/Cargo.toml")
    main = _read("services/speccheck/crates/lua_fastcheck/src/main.rs")

    assert '"crates/lua_fastcheck"' in workspace
    assert 'name = "lua-fastcheck"' in manifest
    assert 'features = ["luajit", "vendored"]' in manifest
    assert "mlua::Lua" in main
    assert "LuaSandboxViolationError" in main


def test_lua_hooks_cover_sandbox_dialect_and_isolation() -> None:
    hooks = {
        ".githooks/check-lua-sandbox.py": "LuaSandboxViolationError",
        ".githooks/check-lua-test-sandbox.py": "LuaSandboxViolationError",
        ".githooks/check-lua-test-isolation.py": "after_each",
        ".githooks/check-luajit-dialect.py": "luajit -bl",
    }
    for path, marker in hooks.items():
        text = _read(path)
        assert marker in text
        assert "*.lua" in text


def test_luacheck_and_buildspecs_have_lua_shards() -> None:
    luacheck = _read(".luacheckrc")
    assert 'std = "luajit"' in luacheck
    assert '"xf"' in luacheck
    assert '"ngx"' in luacheck
    for path in (
        ".codebuild/lint.yml",
        ".codebuild/test-backend.yml",
        ".codebuild/coverage.yml",
        ".codebuild/sidecar-builds.yml",
    ):
        text = _read(path)
        assert "run-lua-quality.sh" in text or "lua" in text
        assert "quality_cores" in text


def test_lua_docs_and_fixture_contract_exist() -> None:
    for path in (
        "docs/specs/fr-lua-testing-toolchain.md",
        "docs/development/testing-guide.md",
        "docs/operations/lua-test-runbook.md",
        "scripts/lua_busted_helper.lua",
        "apps/governance/lua_runtime/advisors/tests/fixtures/claude_code_pretooluse.json",
        "apps/governance/lua_runtime/advisors/tests/fixtures/codex_pre_tool_use.json",
        "apps/governance/lua_runtime/advisors/tests/fixtures/gemini_extension.json",
        "frontend/nginx-lua/tests/ngx_mock.lua",
    ):
        assert (ROOT / path).exists(), path
    spec = _read("docs/specs/fr-lua-testing-toolchain.md")
    assert "[SPEC FRESHNESS: reviewed_at=2026-05-25" in spec
    assert "LuaJIT 2.1" in spec
    assert "busted" in spec
    assert "luacov" in spec
