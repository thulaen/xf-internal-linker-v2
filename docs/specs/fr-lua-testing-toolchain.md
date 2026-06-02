---
title: Lua testing toolchain
source_types:
  - technical_doc
---

# Lua Testing Toolchain

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Behavior

Given Lua is now a project language, when a commit adds or edits Lua code, then the code is checked with LuaJIT 2.1, tested with busted, scanned by luacheck, measured by luacov, and checked for sandbox violations before commit.

Given Lua code has matching busted specs, when the Lua quality runner finishes, then the Docker-built `lua-mutmut` tool writes `reports/lua/mutation.json` and fails unless every viable Lua mutant is killed.

## Source-Backed Choices

- LuaJIT 2.1 is the runtime because the official LuaJIT docs identify 2.1 as the current documentation branch and describe LuaJIT as a Lua 5.1-compatible runtime with extensions. Source: https://luajit.org/running.html and https://luajit.org/extensions.html
- busted is the test framework because its official docs describe it as a Lua unit test framework that works with LuaJIT. Source: https://lunarmodules.github.io/busted/
- luacheck is the lint tool because its documentation describes command-line checks for Lua files and supports the `luajit` standard. Source: https://luacheck.readthedocs.io/en/stable/cli.html
- luacov is the coverage tool because its documentation says scripts load the `luacov` module and then produce a report. Source: https://lunarmodules.github.io/luacov/
- lua-quickcheck is the property-test tool because its LuaRocks page describes random input generation and shrinking for Lua. Source: https://luarocks.org/modules/primordus/lua-quickcheck
- OpenResty handler tests use an `ngx` mock for unit tests and leave full nginx behavior to integration tests. The OpenResty testing guide documents that runtime behavior can differ across test modes, so unit tests and runtime tests must remain separate. Source: https://openresty.gitbooks.io/programming-openresty/content/testing/test-modes.html

## Tool Versions

The pinned versions live in `.tool-versions` and Docker build arguments:

- LuaJIT: `2.1.0-beta3`
- LuaRocks: `3.11.1`
- busted: `2.2.0-1`
- luacheck: `1.2.0-1`
- luacov: `0.16.0-1`
- luacov-cobertura: `0.2-2`
- lua-quickcheck: `0.2-4`

## Test Layout

Each Lua ownership area has its own tests next to the Lua files:

- Content format filters: `apps/content/format_filters/tests/`
- Anchor shapes: `apps/suggestions/anchor_shapes/tests/`
- OpenResty edge handlers: `frontend/nginx-lua/tests/`
- Lefthook Lua hooks: `.githooks/lua/tests/`
- Cross-agent advisors: `apps/governance/lua_runtime/advisors/tests/`
- Redis scripts: `apps/<module>/redis_scripts/tests/`

## Sandbox Rules

Production Lua and Lua tests must use the capability API. Direct `io`, `os`, `debug`, `require`, `loadfile`, and `dofile` calls are blocked by the Python hooks and by the sandbox loader.

[SPEC CITED: feature=fr-lua-testing-toolchain kind=technical_doc id=https://luajit.org/running.html verified_at=2026-06-02]
