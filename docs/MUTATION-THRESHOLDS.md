# Mutation Kill-Rate Thresholds

**This file is the authoritative source of mutation kill-rate thresholds. `config/mutation-routing.json` `kill_rate_gates` is the runtime fallback and MUST mirror these values. When the K8S.19 adapters land, they read thresholds from THIS file.**

[SPEC FRESHNESS: reviewed_at=2026-06-01 next_review=2026-06-30]

## What a mutation kill-rate is (plain English)

A mutation test makes tiny on-purpose changes to the code (called "mutants") and then runs the test suite. If a test fails because of the change, the mutant is "killed" — that proves a test was actually guarding that line. If every test still passes after the change, the mutant "survived" — that means the tests did not really check that behavior.

The kill-rate is the share of mutants the tests kill. A floor of `0.90` means at least 90% of mutants must be killed for that language to pass the gate.

## User preference (the target)

The mutation kill-rate target is **greater than 90% where practical, not 100%**. Do not chase every last surviving mutant — once a language is at or above its floor and the remaining survivors are genuinely equivalent or low-value, stop. Reserve real test-driven fixes for survivors that expose a true gap in the tests.

## Authoritative thresholds (per language)

These are the exact values currently in `config/mutation-routing.json` `kill_rate_gates`. There is zero split-brain: the table below and the JSON match exactly.

| Language    | Kill-rate floor |
|-------------|-----------------|
| python      | 0.90            |
| cpp         | 0.80            |
| go          | 0.45            |
| typescript  | 0.70            |
| rust        | 0.75            |
| haskell     | 0.70            |

## Per-language sections

### python — floor 0.90
Tooling: `mutmut` in the `backend` container. Python carries the most business logic in this repo, so it holds the highest floor.

### cpp — floor 0.80
Tooling: `mull` in the `compiled-tools` container. Hot-path kernels with focused unit binaries; high floor because these paths are performance- and correctness-critical.

### go — floor 0.45
Tooling: `go-mutesting` in the `compiled-tools` container. Lower floor reflects the smaller, newer Go sidecar surface and the higher share of equivalent mutants in Go's generated and glue code. Raise this as the Go test surface matures.

### typescript — floor 0.70
Tooling: `stryker` against the `frontend` workspace. Mid floor for UI logic.

### rust — floor 0.75
Tooling: `cargo-mutants` against `services/speccheck`.

### haskell — floor 0.70
Tooling: `mucheck` against `services/findbugs-haskell`.

## Per-module overrides (finer-grained, may be added later)

Per-language floors are the baseline. Finer-grained per-module overrides may be added later for individual modules or services. **An override may only raise the bar for a specific module — it must never lower the per-language floor.** If a module needs stricter coverage (for example a security- or money-critical module), set a higher per-module value here; the per-language floor remains the minimum any module in that language must meet.

(No per-module overrides defined yet.)

## How to keep the two sources in sync

1. Edit the table in this file first.
2. Mirror the exact same numbers into `config/mutation-routing.json` `kill_rate_gates`.
3. The JSON carries `_kill_rate_gates_note` pointing back here as authoritative.
