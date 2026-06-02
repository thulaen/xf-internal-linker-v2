# Development Testing Guide

## Lua Tests

Lua tests live beside each Lua ownership area. Use busted test files named `*_spec.lua`.

Run the local Lua quality wrapper:

```bash
bash scripts/run-lua-quality.sh
```

The wrapper uses `scripts/quality_cores.sh` to choose the worker count. `QUALITY_CORES` means the number of parallel workers the test tool may use. Set `XF_QUALITY_CORES=2` to request two workers.

Lua tests run through the sandbox rule. That means scripts use `xf.*` capabilities instead of direct `io`, `os`, `debug`, or `require` calls.

Coverage comes from luacov. The target is more than 90 percent on touched Lua files. Mutation testing comes from the repo-owned Rust/mlua `lua-mutmut` tool and must kill every viable mutant for touched Lua files.
