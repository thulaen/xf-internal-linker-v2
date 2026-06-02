# FR: Database Connection-Reset Resilience For Maintenance Tasks

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]
[SPEC CITED: feature=db-connection-reset-resilience kind=technical_doc id=https://www.psycopg.org/psycopg3/docs/basic/transactions.html verified_at=2026-06-02T00:00:00Z]
[SPEC CITED: feature=db-connection-reset-resilience kind=technical_doc id=https://docs.djangoproject.com/en/5.2/ref/databases/ verified_at=2026-06-02T00:00:00Z]
[SPEC CITED: feature=db-connection-reset-resilience kind=technical_doc id=https://www.postgresql.org/docs/current/errcodes-appendix.html verified_at=2026-06-02T00:00:00Z]
[SPEC CITED: feature=db-connection-reset-resilience kind=technical_doc id=https://www.postgresql.org/docs/current/functions-sequence.html verified_at=2026-06-02T00:00:00Z]
[SPEC CITED: feature=db-connection-reset-resilience kind=technical_doc id=https://docs.djangoproject.com/en/5.2/topics/db/transactions/ verified_at=2026-06-02T00:00:00Z]

## Purpose

Two background-maintenance behaviours in this project can leave the database
connection or the id sequences in a broken state after a partial failure. This
spec describes the source-backed fix for both, so the same connection can keep
working after a failed query and so inserts cannot collide with restored rows.

The two behaviours are:

1. **Poisoned-connection reset.** When a query inside a maintenance task fails,
   the pooled PostgreSQL connection is left inside a failed transaction. Any
   later query on that same connection — including the write that records the
   error — fails with PostgreSQL error code `25P02`
   (`in_failed_sql_transaction`). The fix closes the poisoned connection in the
   `except` block of the nightly retention purges and the monthly tune tasks,
   guarded by `not connection.in_atomic_block`, so the connection pool hands the
   next step a clean connection.

2. **Sequence reset after restore.** After a database is restored from a backup,
   each table's auto-increment id sequence can point below the largest id that
   was restored. The next insert then reuses an id that already exists and fails
   with a duplicate-key error. The fix resets every id sequence to
   `MAX(id)` after a restore using PostgreSQL `setval`, so the next insert picks
   the first free id.

## Background And Source Of Truth

### Behaviour 1 — why a failed query poisons the connection

The PostgreSQL adapter `psycopg` (version 3) opens an implicit transaction on
the first statement and keeps it open until a commit or rollback. The
psycopg transaction documentation states that once any statement raises an
error, the whole transaction is marked as failed, and every later statement on
that connection is rejected until a `ROLLBACK` runs
(`https://www.psycopg.org/psycopg3/docs/basic/transactions.html`).

PostgreSQL exposes this rejected state as SQLSTATE `25P02`
(`in_failed_sql_transaction`), listed in the official error-code appendix
(`https://www.postgresql.org/docs/current/errcodes-appendix.html`). The
plain-English meaning of `25P02` is: "this transaction already hit an error, so
I will not run any more statements on it until you roll back."

Django keeps one long-lived connection per worker (controlled by `CONN_MAX_AGE`)
and reuses it across tasks, as described in the Django databases reference
(`https://docs.djangoproject.com/en/5.2/ref/databases/`). When a maintenance
task runs raw SQL outside Django's atomic-block management and the SQL fails,
the connection is left in the `25P02` state. The next step in the same task —
and, critically, the `ErrorLog` write that is supposed to record the failure —
then fails for a confusing secondary reason instead of the real one.

`django.db.connection.in_atomic_block` is the documented way to ask Django
whether the current code is inside an `atomic()` block
(`https://docs.djangoproject.com/en/5.2/topics/db/transactions/`). Closing a
connection that Django is managing inside an `atomic()` block would break
Django's own rollback bookkeeping, so the guard `not connection.in_atomic_block`
is required: only close the connection when Django is not already managing a
transaction frame around it.

### Behaviour 2 — why sequences must be reset after a restore

PostgreSQL implements auto-increment ids with sequence objects. A sequence has
its own current value that is independent of the table's rows. When a table is
loaded from a backup dump that inserts explicit id values, the sequence is not
automatically advanced past those values unless the dump also restores the
sequence state. The function `setval(regclass, bigint)` sets a sequence's
current value, and the next call to `nextval` returns the value after it, as
described in the PostgreSQL sequence-function documentation
(`https://www.postgresql.org/docs/current/functions-sequence.html`).

If the sequence is left pointing at a value at or below `MAX(id)`, the next
insert asks the sequence for an id that a restored row already uses, and the
unique primary-key constraint rejects the insert with a duplicate-key error. The
fix runs `setval('<table>_id_seq', (SELECT MAX(id) FROM <table>))` for every
restored table so the sequence resumes one past the largest restored id.

## Behavior

### Connection reset (Behaviour 1)

Given a nightly retention purge or a monthly tune task is running and a query
inside it raises a database error, when control reaches the task's `except`
block and `connection.in_atomic_block` is `False`, then the task closes the
poisoned pooled connection via `connection.close()` before it records the error,
so the `ErrorLog` write and any later step in the task run on a fresh connection
instead of failing with PostgreSQL `25P02`.

Given the same task is running inside a Django `atomic()` block (so
`connection.in_atomic_block` is `True`), when a query fails, then the task does
NOT call `connection.close()`, because Django owns the transaction frame and
will roll it back itself; closing the connection here would break Django's
rollback bookkeeping.

Given the poisoned connection was closed, when the next query runs, then Django
transparently opens a new connection from the pool, the new connection is clean,
and the query succeeds.

### Sequence reset (Behaviour 2)

Given a database has just been restored from a backup and one or more tables
were loaded with explicit id values, when the post-restore sequence-reset step
runs, then for every restored table it executes
`setval('<table>_id_seq', GREATEST(MAX(id), 1))` so the sequence points at the
largest restored id.

Given the sequence has been reset to `MAX(id)`, when the next row is inserted
into that table, then the sequence returns `MAX(id) + 1`, the id is free, and the
insert succeeds without a duplicate-key error.

Given a restored table is empty (no rows), when the sequence-reset step runs,
then `setval` is called with a floor of `1` so the next insert starts at id `1`
and the call does not fail on a `NULL` `MAX(id)`.

## Budgets

- Connection close on failure: a single `close()` call, well under 5 ms; the
  pooled reconnect happens lazily on the next query.
- Sequence reset after restore: one `setval` round-trip per restored table,
  expected under 50 ms total for the project's table count, and run once per
  restore rather than on any hot path.

## Non-Goals

- This spec does not change any ranking signal, pipeline algorithm, scoring
  weight, or API endpoint.
- This spec does not add a new model, migration, or schema change.
- This spec does not wrap every maintenance query in a new retry loop; it only
  guarantees the connection is usable for the error-recording write and the next
  step, and that ids do not collide after a restore.
- This spec does not change Django's `CONN_MAX_AGE` or connection-pool sizing.

## Risk List

- Closing a connection that Django is managing inside an `atomic()` block would
  corrupt Django's rollback state. Mitigation: the `not connection.in_atomic_block`
  guard prevents the close in that case.
- Resetting a sequence to a wrong value could either skip ids (harmless) or
  reuse ids (harmful). Mitigation: the reset uses `MAX(id)` with a floor of `1`,
  so the next id is always strictly greater than every existing id and never
  below `1`.
- A restore that touches a table with a non-standard sequence name would be
  missed by a naive `<table>_id_seq` guess. Mitigation: the reset derives the
  owning sequence from `pg_get_serial_sequence` where the name is not the default
  pattern, matching PostgreSQL's documented sequence-ownership behaviour.
