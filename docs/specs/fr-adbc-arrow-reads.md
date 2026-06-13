# ADBC Arrow-native Postgres reads — spec

[SPEC FRESHNESS: reviewed_at=2026-06-13 next_review=2026-09-13]
[SPEC CITED: feature=adbc-arrow-reads kind=technical_doc id=https://arrow.apache.org/adbc/ verified_at=2026-06-13]

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | ADBC Arrow-native Postgres reads |
| **Helper module** | `backend/apps/analytics/services/adbc_reader.py` (`postgres_uri`, `read_sql_polars`) |
| **Call sites** | `backend/apps/analytics/telemetry_rollups.py::_refresh_snapshot` · `backend/apps/analytics/tasks.py::_snapshot_gsc_clicks` |
| **Tests** | `backend/apps/analytics/services/tests_adbc_reader.py` (URI builder) · `tests_telemetry_rollups.py` + `tests_traffic_spikes.py` (round-trip parity, TransactionTestCase) |
| **Dependencies** | `adbc-driver-postgresql==1.3.0`, `adbc-driver-manager==1.3.0` (runtime image) |
| **Default state** | Always on — it is the only read path for these two snapshot exports (one-way replacement of the prior ORM `values_list` + `zip` path). |

## 2 · Problem

The two analytics snapshot jobs export tens of thousands of Postgres rows into
Polars/Parquet. The Django ORM `values_list()` returns the result as a list of
Python tuples, which we then `zip(*rows)` back into columns — two full passes
that allocate a throwaway Python object per cell. The downstream consumer
(Polars → Parquet → DataFusion) is columnar Arrow end to end; the ORM step is
the only row-oriented hop.

## 3 · Approach

ADBC (Arrow Database Connectivity) is the Arrow project's database API. The
PostgreSQL driver streams a query result directly as an Arrow table, which
Polars wraps with `pl.from_arrow` at zero copy. `read_sql_polars(sql, params)`
runs one query over the ORM's *current* default connection and returns a Polars
DataFrame; `postgres_uri()` builds the libpq URI from
`django.db.connection.settings_dict` (which carries the active database name —
the **test** database during tests, the live database in production), with
URL-encoded credentials and `%s` parameter binding (no string-formatted values).

## 4 · Behaviour preserved

The SQL selects the same columns, in the same order, with the same filters as
the retired ORM query (date window for telemetry; `source='gsc'` + date range
for GSC clicks). The Parquet schema written is unchanged (Polars `Date` +
integer + utf8 columns), so the DataFusion queries over the snapshot are
untouched. Table names come from each model's `_meta.db_table` (trusted, never
user input).

## 5 · Test-visibility consequence

ADBC opens its **own** libpq connection, so it sees only COMMITTED rows. The two
round-trip tests therefore use `TransactionTestCase` (which commits fixtures)
rather than the default transactional `TestCase` (whose writes are never
committed and so are invisible to a second connection). This is the single
behavioural cost of the change and is documented at each converted test class.

## 6 · Scaling

At 10× the current row count the Arrow path's advantage grows (the per-row
Python object cost the ORM pays scales linearly; the columnar transfer does
not). At 100× the snapshot export remains a single streamed query; the limiting
factor becomes Parquet write throughput, not the read.

## 7 · References

- Apache Arrow ADBC — https://arrow.apache.org/adbc/
- ADBC PostgreSQL driver — https://arrow.apache.org/adbc/current/driver/postgresql.html
