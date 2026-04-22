# Scheduled Updates Architecture

Authoritative spec for the serial, pause-resumable, 13:00–23:00-local
job runner in `backend/apps/scheduled_updates/`. Every scheduled job
referenced by any pick spec lives inside this architecture. If the
runner contract changes, edit this file **first** and update the
corresponding pick specs next.

Related code: `apps/scheduled_updates/{runner.py, registry.py,
alerts.py, window.py, lock.py, broadcasts.py, views.py, models.py}`.

---

## 1 · Why this design

- **Laptop reality.** Host is a single laptop. It sleeps at night.
  Jobs that assume "always on" fail silently and accrete alerts.
- **Operator surface.** Every scheduled update must be visible in the
  dashboard with progress, pause/resume, missed-run alerting, and a
  "Run Now" button for catch-up.
- **No fleet scheduler.** Celery Beat is the only trigger — we don't
  bolt on Kubernetes CronJobs or Airflow. The dependency graph stays
  in-repo.
- **Determinism.** One job at a time, with a Redis lock, means logs
  are linear and CPU/RAM contention is bounded.

## 2 · Time window — 13:00 to 23:00 local

- **Fixed window.** All scheduled kick-offs fall inside
  `crontab(hour='13-22', minute=0)` (the runner itself is called
  every 5 min within that window to pick up the next ready job).
- **Rationale.** Chosen by operator on 2026-04-22 after moving from
  the original 1 pm – 9 pm window to 1 pm – 11 pm. Laptop sleeps
  around 23:00; the guard forbids *starting* a new job if
  `now + estimate_seconds > 23:00:00`. Jobs that have already
  started may run past 23:00 if they're at a checkpoint (see §5).
- **Serial.** The runner holds a Redis lock
  (`scheduled_updates:runner`) with `SET NX EX=900`, refreshed by
  the worker heartbeat. While the lock is held no other job starts.
  Inside a job, `joblib.Parallel(n_jobs=-1)` is free to use all
  cores.
- **Catch-up.** If the runner wakes up and finds a job whose
  `last_success_at` is older than `cadence_seconds`, it marks
  the job `state=missed` and surfaces a deduped alert (see §6).

## 3 · Job registry

Jobs register via the `@scheduled_job(...)` decorator in
`apps/scheduled_updates/registry.py`. The decorator does two things:

1. Mints a `JobDefinition` and drops it into the in-process
   `JOB_REGISTRY` dict keyed on the job's `key` string.
2. On Django startup (AppConfig.ready), the `seed_registry_to_db()`
   call upserts a `ScheduledJob` row per registered key — so the
   dashboard shows the job even before its first run.

**Contract for a job function:**

```python
@scheduled_job(
    key="trustrank_propagation",
    display_name="TrustRank propagation",
    cadence_seconds=86400,          # 24 h
    priority=Priority.HIGH,
    estimate_seconds=5 * 60,
    multicore=True,
    depends_on=("trustrank_auto_seeder", "pagerank_refresh"),
)
def run_trustrank(checkpoint: JobCheckpoint) -> None:
    ...
```

- `key` is the stable identifier; never change it without a migration.
- `cadence_seconds` is the **target** cadence; the runner decides
  actual firing inside the 13–23 window.
- `priority` is one of `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`. Higher
  priorities are picked first when multiple jobs are ready.
- `estimate_seconds` drives the window guard — if `now + estimate >
  23:00:00` the job won't start until tomorrow's window.
- `multicore` is advisory — used by dashboard to label the card.
- `depends_on` blocks a job from starting until every named upstream
  job has a success within the current day's window.

## 4 · The full job list (plan-spec alignment)

The 20 jobs below cover the shipped 52-pick roster. Each row must
match one pick spec under `docs/specs/pick-NN-*.md`; if a pick is
periodic and not listed here, the pick spec is incomplete.

| Priority | Key | Cadence | Estimate | Multicore | Dependencies | Pick # |
|---|---|---|---|---|---|---|
| critical | `feedback_aggregator_ema_refresh` | daily 13:05 | 2 min | no | — | 40 |
| critical | `bloom_filter_ids_rebuild` | weekly (Mon 13:10) | 5 min | yes | — | 4 |
| critical | `link_freshness_decay` | daily 13:15 | 5 min | no | — | (pre-existing META-15) |
| critical | `crawl_freshness_scan` | daily 13:30 | 15–60 min | yes | — | 10 |
| high | `pagerank_refresh` | daily 14:30 | 5 min | yes | — | (pre-existing META-06) |
| high | `personalized_pagerank_refresh` | daily 14:40 | 8 min | yes | `pagerank_refresh` | 36 |
| high | `hits_refresh` | daily 14:50 | 5 min | yes | — | 29 |
| high | `trustrank_auto_seeder` | daily 15:00 | 2 min | no | `pagerank_refresh` | 51 |
| high | `trustrank_propagation` | daily 15:05 | 5 min | yes | `trustrank_auto_seeder` | 30 |
| high | `weight_tuner_lbfgs_tpe` | weekly (Sun 16:00) | 20–40 min | yes | — | 41 + 42 |
| high | `meta_hyperparameter_hpo` | weekly (Sun 16:45) | 60–120 min | yes | `weight_tuner_lbfgs_tpe` | 42 (Option B) |
| medium | `lda_topic_refresh` | weekly (Tue 15:30) | 30–60 min | yes | — | 18 |
| medium | `kenlm_retrain` | weekly (Wed 15:30) | 15–30 min | yes | — | 23 |
| medium | `node2vec_walks` | weekly (Thu 15:30) | 20–45 min | yes | — | 37 (deferred) |
| medium | `collocations_pmi_rebuild` | weekly (Fri 15:30) | 10 min | yes | — | 24 |
| medium | `entity_salience_retrain` | weekly (Sat 15:30) | 10 min | yes | — | 26 |
| medium | `product_quantization_refit` | monthly | 30 min | yes | — | 20 |
| medium | `near_duplicate_cluster_refresh` | daily 17:00 | 10 min | yes | — | (pre-existing META-38) |
| low | `cascade_click_em_re_estimate` | weekly (Sun 18:00) | 5 min | no | — | 34 |
| low | `position_bias_ips_refit` | weekly (Sun 18:10) | 5 min | no | — | 33 |
| low | `factorization_machines_refit` | weekly (Sun 18:20) | 10 min | yes | — | 39 (deferred) |
| low | `bpr_refit` | weekly (Sun 18:40) | 15 min | yes | — | 38 (deferred) |
| low | `reservoir_sampling_rotate` | daily 19:00 | < 1 min | no | — | 48 |
| low | `analytics_rollups` | daily 20:00 | 5 min | no | — | (pre-existing) |
| low | `jobalert_dedup_cleanup` | daily 22:45 | < 1 min | no | — | infra |

**Deferred jobs.** Node2Vec, BPR, and FM are registered but marked
`enabled=False` until their pip deps (`node2vec` / `implicit` / `pyfm`)
are approved. The registry exposes them in the dashboard so operators
can see they exist; the runner skips them with reason
`deferred_awaiting_pip_dep`.

## 5 · Checkpoint / pause-resume contract

Every job function receives a `JobCheckpoint` that exposes:

- `report_progress(pct: float, message: str)` — pushes a WebSocket
  frame on the `scheduled_updates` Channels group.
- `check_pause_token()` — raises `PauseRequested` if the operator
  clicked Pause. The caller must catch it at a *checkpoint boundary*
  (end of a batch, between graph iterations) and persist partial state.
- `save_state(payload: dict)` / `load_state() -> dict` — persists
  opaque JSON onto `ScheduledJob.checkpoint_state`. Resumed jobs load
  this and continue from where they left off.

**Rule.** A job that takes > 30 s must call `report_progress` at
least every 10 s and `check_pause_token` at least every 30 s. Jobs
that don't checkpoint are undebuggable and will be rejected in
review.

## 6 · Deduped missed-job alerts

Database table: `scheduled_updates_jobalert`.

Unique constraint: `UNIQUE(job_key, alert_type, calendar_date)`.

Every (job, type, day) triple yields **exactly one row**. The runner
uses `update_or_create` so a missed job that's still missed the next
tick updates `last_seen_at`, not inserts a duplicate.

Alert lifecycle:

1. **Raised.** Runner detects `last_success_at < now - cadence` on a
   13:00 wake — inserts/updates a row with `alert_type="missed"`.
2. **Acknowledged.** Operator clicks ✕ → `acknowledged_at = now`.
   Row hides from the active list but stays in history.
3. **Resolved.** Next successful run of the job auto-sets
   `resolved_at` on every open alert for that `job_key`.
4. **Pruned.** `jobalert_dedup_cleanup` job deletes rows older than
   30 days.

Dashboard: `mat-badge` on the Scheduled Updates tab shows the count
of alerts where `acknowledged_at IS NULL AND resolved_at IS NULL`.

## 7 · Option B — meta hyperparameter auto-tuning (pick #42 / TPE)

The `meta_hyperparameter_hpo` job runs a weekly `optuna.Study` that
optimises NDCG@10 over an offline evaluation set. The study's
search space is the union of every pick spec's `TPE search space`
column for hyperparameters marked **TPE-tuned = Yes**.

Implementation layout:

```
apps/pipeline/services/
├── meta_hpo.py        # TPE study + trial runner
└── meta_hpo_eval.py   # Reservoir-sampled offline NDCG evaluator
```

- **Sampler.** `optuna.samplers.TPESampler` (Bergstra et al. 2011 NeurIPS).
- **Pruner.** `optuna.pruners.MedianPruner` — stops trials that are
  obviously worse than the running median.
- **Trial count.** 200 per weekly run (fits inside the 60–120 min
  estimate on the observed hardware).
- **Storage.** SQLite DB at `var/optuna/meta_hpo.db` so studies
  persist across laptop reboots and missed windows.
- **Application.** After the study finishes, the job writes the
  best trial's parameters back into AppSetting. A migration
  snapshot is *not* created per-run — only the manual
  "Accept HPO result" button in the dashboard commits the new
  values to the Recommended preset.

**Guard rails.**

- Every TPE-tuned hyperparameter has a `clip_min` / `clip_max` that
  must match its pick spec's search space. The job never applies
  values outside these bounds.
- Correctness parameters (Bloom FPR, HLL precision, Kernel SHAP
  nsamples, ACI coverage target) stay **fixed**; their specs mark
  them `TPE-tuned = No`.
- A dashboard card shows the last study's best trial + delta vs the
  currently-applied preset. Operators approve or reject before new
  values take effect.

## 8 · Broadcast channel

`channels_redis` group name: `scheduled_updates`.

Frames:

```json
{"type": "job.progress", "job_key": "...", "pct": 0.42, "message": "embedding batch 41/98"}
{"type": "job.state",    "job_key": "...", "state": "running"}
{"type": "alert.raised", "job_key": "...", "alert_type": "missed"}
{"type": "alert.resolved", "job_key": "...", "count": 2}
```

Every message is throttled server-side to 1 per 500 ms per job to
avoid DOM-update floods when many tabs are open.

## 9 · Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Job crashes with exception | Runner wraps in try/except → `state=failed`, `alert_type="failed"` | Operator retries via Run Now |
| Job exceeds its estimate | `now + remaining > 23:00` → runner suspends at next checkpoint, resumes next window | Automatic |
| Operator clicks Pause | Worker raises `PauseRequested` at next `check_pause_token` | State persisted; Resume continues |
| Redis lock expires mid-run | TTL is 900 s, heartbeat refresh every 60 s | Jobs > 15 min without a checkpoint call get treated as failed |
| Runner skipped (laptop off) | Next wake-up's catch-up scan raises `alert_type="missed"` | Deduped per day |

## 10 · Open questions

- **Multi-user editing of preset values.** If two operators accept
  two different HPO results on the same day, whose wins? Current
  answer: last-write-wins on the AppSetting row. Revisit if >1 admin
  is common.
- **Laptop wakes mid-job that was paused overnight.** Runner currently
  resumes at next 13:00; consider a "resume on wake" hook if the
  laptop wakes before 13:00.
- **Fleet deployment.** If the laptop ever gets replaced by a
  server, the Redis lock + single-runner assumption generalises
  (Redis lock is cluster-safe), but the 13–23 local window stops
  making sense in a 24/7 environment. This spec would need a
  "window source" setting.
