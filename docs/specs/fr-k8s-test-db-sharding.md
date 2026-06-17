# FR - Kubernetes Test Database Sharding (SLICE-14 closeout)

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Status

Implemented as reusable backend tooling. The live cluster pipeline can now create
per-shard test databases from one migrated template database and clean old shard
databases by age. PgBouncer remains in session mode for app safety; shard
database creation connects directly to Postgres through the admin host settings.

## Source Of Truth

- `backend/apps/audit/services/test_database_shards.py` builds safe shard
  database names, creates a database from a template, drops a shard database, and
  selects expired shard databases for cleanup.
- `backend/apps/audit/management/commands/rebuild_test_db_template.py` rebuilds
  the template database and runs migrations against that template.
- `backend/apps/audit/management/commands/cleanup_test_shard_databases.py`
  removes expired shard databases. `--dry-run` lists them without dropping
  anything.
- `backend/apps/audit/tests_test_database_shards.py` covers safe names, cleanup
  selection, and the dry-run command paths.

## Rules

- Shard database names use the format `xf_t_YYYYMMDDHHMMSS_<run>_s<N>`.
- The direct admin connection refuses `pgbouncer` as the host. Database clone
  work must use Postgres directly because PgBouncer transaction pooling is not a
  safe place for clone-time advisory locks.
- The helper never closes Django's active default test connection. The template
  rebuild command uses a temporary Django database alias and closes only that
  alias.

## Proof

Given a cluster test run needs isolated shard databases, When it calls the
shared helper, Then every shard gets a timestamped safe database name cloned from
the same migrated template.

Given old shard databases remain after a failed run, When cleanup runs with an
age limit, Then only names matching the shard naming pattern and older than the
limit are selected.
