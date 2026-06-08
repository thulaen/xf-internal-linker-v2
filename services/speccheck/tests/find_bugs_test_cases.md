# Find-Bugs Test Cases

These test cases support `docs/specs/fr-rust-speccheck.md` and bound the
`speccheck find-bugs` implementation.

## Django N+1 query

Given a Python file has a `for` loop
And the loop body calls `.objects.filter(...).first()`
When the operator runs `speccheck find-bugs <path>`
Then the JSON report contains one `RUSTBUG-PERF-001` finding at the query line.

## Query outside loop

Given a Python file calls `.objects.filter(...).first()` outside a loop
When the operator runs `speccheck find-bugs <path>`
Then `RUSTBUG-PERF-001` is not emitted.

## Blocking HTTP in async view

Given a Python file has an `async def` block
And the block body calls `requests.get(...)`
When the operator runs `speccheck find-bugs <path>`
Then the JSON report contains one `RUSTBUG-PERF-004` finding at the blocking
HTTP line.

## Unbatched save loop

Given a Python file has a `for` loop
And the loop body calls `.save()`
When the operator runs `speccheck find-bugs <path>`
Then the JSON report contains one `RUSTBUG-PERF-008` finding at the save line.

## Sync ORM in async view

Given a Python file has an `async def` block
And the block body calls `.objects.get(...)`
When the operator runs `speccheck find-bugs <path>`
Then the JSON report contains one `RUSTBUG-CONC-005` finding at the ORM line.
