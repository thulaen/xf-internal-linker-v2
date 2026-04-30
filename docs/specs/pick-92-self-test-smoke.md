# Pick 92 - Startup Self-Test Smoke Suite

## Citation

Salus and Whittaker, 1997, self-test patterns for systems that verify their own invariants at startup.

## Required Behavior

On Django startup after migrations, the application runs a short structural audit of per-content artefact tables. Each table that stores derived content artefacts must have:

- a no-duplicates invariant;
- a supersede marker when rows can replace older rows;
- a retention timestamp so old rows can be cleaned safely.

## Operator Message

When a new table is missing the no-duplicates invariant, the system logs this exact warning to the error log:

`New table TABLE_NAME added without no-dups invariant. See NO-DUPLICATES.md to fix.`

The smoke test is controlled by `system.startup_smoke_test_enabled`, which defaults to true in the Recommended preset.
