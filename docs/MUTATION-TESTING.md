# Mutation Testing

Mutation testing checks how strong your tests are by deliberately breaking the code (mutating operators, inverting conditionals, deleting statements) and then running the test suite. If the tests still pass after the code has been broken, the mutation "survived" — meaning the test suite is too weak to catch that regression. Surviving mutants = non-zero exit; the CI gate blocks merge.

This is the partner discipline to randomised test order (see `docs/CI-GATES.md`): randomisation catches order-dependent tests; mutation catches tests-that-don't-actually-assert.

## Scope (initial)

Mutation testing is **scoped to one module per language** to start. The CI cost is high (each mutant runs the full test suite). The scope expands one module per PR via the AutoIssue ratchet (see AutoIssue #162 sweep tracker).

| Language | Tool | Initial scope | Test command |
|---|---|---|---|
| Python | mutmut 2.5.0 | `backend/apps/auto_issues/services/fingerprinting.py` | `python -m pytest apps/auto_issues -p randomly -x -q --no-cov` |
| TypeScript | Stryker 8.x | `frontend/src/app/core/services/a11y-prefs.service.ts` | `karma` (project's standard Karma runner) |
| C++ | Mull 0.21+ | `backend/extensions/test_simsearch` (scaffold only) | `ctest --output-on-failure` |

## Running locally

### Python (mutmut)

```bash
cd backend
mutmut run \
  --paths-to-mutate=apps/auto_issues/services/fingerprinting.py \
  --runner="python -m pytest apps/auto_issues -p randomly -x -q --no-cov" \
  --processes=2
mutmut results
```

`mutmut results` exits non-zero if any mutant survived. To inspect a specific survivor: `mutmut show <id>`.

### Angular (Stryker)

```bash
cd frontend
npx stryker run
```

Reports land in `frontend/reports/stryker.html` (visual) and `frontend/reports/stryker.json` (CI-consumable). The `thresholds.break: 40` line in `stryker.config.json` is the hard floor — below 40% mutation score, CI fails.

### C++ (Mull)

Mull requires a Mull-compiled Clang toolchain. Setup steps in `backend/extensions/MUTATION-TESTING-CPP.md` (forthcoming). Until that lands the `cpp-mull` CI job stays in advisory mode behind a `# GATE-DOWNGRADE-JUSTIFICATION:` comment.

## Plain-English summary

Mutation testing pokes holes in the code and watches whether the tests scream. If they don't scream, the tests are too lax. New work is gated against that.

## Pre-push vs CI

| Stage | Scope | Time |
|---|---|---|
| Pre-push | Mutate only files changed in this push | ~3-5 min |
| CI per-PR | Mutate the initial scope module | ~10-20 min |
| CI nightly | Mutate every covered module | ~30-60 min |

See `.githooks/pre-push` for the changed-files wiring.

## Why each tool

- **mutmut** — most popular Python mutation tool; supports parallel runs via `--processes`; integrates with pytest.
- **Stryker** — TypeScript-native; integrates with Karma so we reuse our existing test infrastructure.
- **Mull** — LLVM-based; runs mutants in parallel at the IR level (orders of magnitude faster than source-level mutation for C++).

## Ratchet

Each PR can expand the scope by adding one more file/module to the `paths-to-mutate` config. The goal is to grow coverage incrementally without blowing up CI runtime. New code should be testable enough that mutation testing surfaces no survivors on its first pass — if it does, the tests need more assertions before merge.
