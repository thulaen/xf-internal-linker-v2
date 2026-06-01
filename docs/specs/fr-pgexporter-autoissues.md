# FR — postgres-exporter health findings → AutoIssues, with an always-on "fix 10" quota

[SPEC FRESHNESS: reviewed_at=2026-06-01 next_review=2026-07-01]
[SPEC CITED: feature=pgexporter-autoissues kind=technical_doc id=postgresql-monitoring-stats-17 verified_at=2026-06-01]
[SPEC CITED: feature=pgexporter-autoissues kind=technical_doc id=postgresql-pg-stat-statements-17 verified_at=2026-06-01]
[SPEC CITED: feature=pgexporter-autoissues kind=technical_doc id=prometheus-community-postgres-exporter-0.16 verified_at=2026-06-01]
[SPEC CITED: feature=pgexporter-autoissues kind=technical_doc id=prometheus-text-exposition-format-0.0.4 verified_at=2026-06-01]

## Problem

`postgres-exporter` (the `prometheuscommunity/postgres-exporter` container) already
publishes PostgreSQL health metrics in Prometheus text format on `:9187/metrics`, but
nothing turns a breach (database down, deadlocks, low cache-hit ratio, connection
saturation) into a tracked, fixable AutoIssue. `AutoIssue.SOURCE_PROMETHEUS` exists but
has no picker. The operator wants these problems filed automatically AND a hard,
commit-blocking quota so the backlog cannot be ignored.

## Sources of truth

- **PostgreSQL "Monitoring Database Activity" / cumulative statistics** (`pg_stat_database`:
  `deadlocks`, `xact_commit`/`xact_rollback`, `blks_hit`/`blks_read`) — the canonical
  definitions behind the threshold rules (`postgresql-monitoring-stats-17`).
- **PostgreSQL `pg_stat_statements`** (`queryid`, `query`, `calls`, execution time
  columns) — the canonical source behind the slow-query picker. Backup `COPY public.*`
  exports and GlitchTip's own `issue_events_issue` maintenance updates are operational
  bookkeeping, so the picker filters them before filing app slow-query AutoIssues
  (`postgresql-pg-stat-statements-17`).
- **prometheus-community/postgres_exporter v0.16** — the exact metric names exported
  (`pg_up`, `pg_database_size_bytes`, `pg_locks_count`, `pg_stat_database_*`,
  `pg_stat_activity_count`, `pg_settings_max_connections`) (`prometheus-community-postgres-exporter-0.16`).
- **Prometheus text exposition format 0.0.4** — the `name{labels} value` grammar the
  parser implements (`prometheus-text-exposition-format-0.0.4`).

## Behaviour (Given / When / Then)

- **Given** postgres-exporter is reachable, **When** the picker scrapes `:9187/metrics`,
  **Then** each threshold breach becomes one deduped AutoIssue under `SOURCE_PROMETHEUS`,
  and any previously-open finding whose metric no longer breaches is auto-resolved with a
  two-part `Trap/Fix shape` lesson.
- **Given** `>= 10` `prometheus` AutoIssues are open, **When** any commit runs, **Then**
  the commit is blocked unless `>= 10` were resolved this session. **Given** `< 10` are
  open, **Then** the commit is never blocked (you cannot fix issues that do not exist).

## Threshold rules (each cited above)

| Rule | Metric(s) | Condition | Severity |
|------|-----------|-----------|----------|
| Database down | `pg_up` | `== 0` | critical |
| Deadlocks | `pg_stat_database_deadlocks` | `> 0` (real DBs only) | high |
| Low cache-hit ratio | `pg_stat_database_blks_hit`/`blks_read` | ratio `< 0.99` once `hit+read >= 100` | medium |
| Connection saturation | `pg_stat_activity_count` vs `pg_settings_max_connections` | in-use `> 80%` | high |

System databases (`template0`, `template1`, `postgres`) are excluded from per-database rules.

## Design

- Pure parser + rules: `backend/apps/auto_issues/services/pgexporter_metrics.py`
  (`parse_prometheus_text`, `evaluate_rules`) — no DB, no network, `SimpleTestCase`-testable.
- Orchestration: `backend/apps/auto_issues/services/pgexporter_picker.py`
  (`pick_pgexporter_findings`) — mirrors `vmalert_picker.py`, files via the shared
  `upsert_dedup`, supports `dry_run`.
- Commands: `pick_pgexporter_findings` (writes; `--dry-run`), `verify_always_on_quota`
  (read-only).
- Quota rule: `backend/apps/auto_issues/services/always_on_quota.py`
  (`always_on_quota_status`): PASS iff `open < threshold` OR `resolved >= threshold`.
- Enforcement: `.githooks/check-always-on-quota.py` (config `ALWAYS_ON_SOURCES`),
  wired into `scripts/precommit-docker.sh` after `check-autoissue-quota`. Drought-aware,
  so it never blocks a clean source; Docker-down is a hard FAIL (no skip).
- Schedule: `auto_issues.pgexporter_findings_refresh` (hourly), in
  `backend/config/settings/celery_schedules.py`.

## Why a dedicated gate (not the 30-pick ritual or `_HARD_SOURCE_REQUIREMENTS`)

The 30-pick `[REGISTRY READ]` marker and its hardcoded 10-source regex are intentionally
untouched. Adding `prometheus: 10` to `_HARD_SOURCE_REQUIREMENTS` would block every commit
forever, because hard sources have no drought exemption (0 open still demands 10). The
dedicated drought-aware gate gives the operator's "always-on fix 10" without that trap.

## Verification

See the "Verification" section of the implementation plan: unit tests
(`apps/auto_issues/tests/test_pgexporter_metrics.py`, `test_always_on_quota.py`,
`test_pgexporter_picker.py`, `test_verify_always_on_quota_cmd.py`), a live dry-run smoke
against `:9187`, and `verify_always_on_quota --source prometheus`.
