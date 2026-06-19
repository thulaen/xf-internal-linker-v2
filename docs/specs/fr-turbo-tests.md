---
id: fr-turbo-tests
title: Distributed Test and Coverage Runner (Turbo Tests)
status: active
[SPEC FRESHNESS: reviewed_at=2026-06-01 next_review=2026-06-30]
---

## Purpose

Fan out Python SimpleTestCase unit tests across Dell (60%), Windows (30%), Mint (10%).
Reuses machine_routing.py weighted partition — same logic as the private Bazel mutation coordinator.

## Behaviour (BDD)

Given Python test files containing SimpleTestCase (no DB dependency)
When XF_TURBO_TESTS=1 and scripts/turbo_tests.py runs
Then files are sharded by weight, each shard runs on its machine in parallel,
and the exit code is 0 only if every shard passes.

Given a machine is off at startup
When turbo_tests.py probes reachability
Then its shard redistributes to running machines (fail-open).

## Design

- Reuses machine_routing.py (_select_machines, _partition_weighted, _dispatch_to_machines).
- Local Windows: docker compose run --rm -T backend-quality pytest
- Remote Mint/Dell: docker run with named volume xf_test_repo (separate from xf_mutation_repo).
- SimpleTestCase-only: DB-free tests safe on any machine. DB tests stay Windows-only.

## Citations

[SPEC CITED: feature=fr-turbo-tests kind=technical_doc id=https://testing.googleblog.com/2016/03/how-google-runs-tests-at-scale.html verified_at=2026-06-01]

- Google Testing Blog "How Google Runs Tests at Scale" (2016):
  https://testing.googleblog.com/2016/03/how-google-runs-tests-at-scale.html
- Balinski & Young "Fair Representation" (1982) — Hamilton apportionment.
- pytest-split docs: https://pytest-split.readthedocs.io/en/stable/

## Scope

- Python SimpleTestCase: distributed across 3 machines
- Python TestCase (DB): Windows only (future work)
- Angular / C++ / Go / Rust / Haskell: their existing machines unchanged
