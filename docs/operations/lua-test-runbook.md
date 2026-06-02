# Lua Test Runbook

## Run Locally

1. Build or enter an image that has LuaJIT and LuaRocks installed.
2. Run `bash scripts/install-lua-tools.sh` if the image has not already installed the pinned rocks.
3. Run `bash scripts/run-lua-quality.sh`.

The log line `[quality_cores] tool=busted workers=N ...` tells you how many workers busted used.

## Run On Mint Or Dell Helper

1. Open a shell in the helper image.
2. Confirm `luajit -v`, `busted --version`, `luacheck --version`, and `luacov --version`.
3. Run `bash scripts/run-lua-quality.sh`.

Lua tests use little memory. LuaJIT is about a few megabytes per worker, so eight workers are fine on the planned CodeBuild large runner.

## Run On CodeBuild

The Lua shards are in:

- `.codebuild/lint.yml`
- `.codebuild/test-backend.yml`
- `.codebuild/coverage.yml`
- `.codebuild/sidecar-builds.yml`

CloudWatch proof must come from a real CodeBuild run. Local runs cannot produce that proof.

## Missing Mutation Tool

Lua mutation testing is intentionally unwired. The quality runner prints:

```text
lua-mutmut: total=<N> killed=<N> survived=0 timeout=0 unviable=<N> score=100.00
```
