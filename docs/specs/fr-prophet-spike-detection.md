# Prophet seasonality-aware traffic-spike detection — spec

[SPEC FRESHNESS: reviewed_at=2026-06-13 next_review=2026-09-13]
[SPEC CITED: feature=prophet-spike-detection kind=academic_paper id=doi:10.7287/peerj.preprints.3190v2 verified_at=2026-06-13]

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Prophet traffic-spike detection (FR-023 Part 3) |
| **Service** | `backend/apps/analytics/services/spike_forecast.py` (`detect_spikes`) |
| **Task** | `backend/apps/analytics/tasks.py::detect_traffic_spikes` (Celery beat) |
| **Settings** | `spike_detection.*` seeded by migration `analytics/0012_seed_prophet_spike_settings.py` |
| **Tests** | `backend/apps/analytics/tests_traffic_spikes.py` (real Prophet fits, TransactionTestCase) |
| **Dependency** | `prophet==1.3.0` (runtime image) |
| **Default state** | ON — settings seeded with sensible non-zero values (default-on rule). |

## 2 · Problem

The old detector compared a page's latest daily clicks to its flat 7-day
trailing average and alerted at 4×. That rule flags every ordinary weekly
rhythm (a page reliably busy each Tuesday looks "spiky" every Tuesday) and can
miss a genuine surge on a normally-quiet day because the flat average has no
notion of which day of the week it is.

## 3 · Approach

For each page, fit a Prophet model (Taylor & Letham 2018) with weekly
seasonality over a 90-day history, then forecast the target day and read its
uncertainty upper bound (`yhat_upper`, 95% interval). A page is spiking only
when its actual clicks exceed `max(yhat_upper, noise_floor) × upper_bound_factor`.
Because the model has learned the page's own weekly pattern, an expected busy
day is inside the band (no alert) while an unexpected surge breaks through it.

## 4 · Cost control

Prophet fitting is the expensive step, so it runs only on candidates that
already look unusual: latest clicks above the noise floor AND above the page's
own trailing mean (`_prescreen`). Candidates are capped at `prophet_max_items`
(200), fitted sequentially, and pages with fewer than `min_active_days` (14)
non-zero days are skipped (too little signal to model). Transient memory per
fit is ~100–200 MB inside the existing Celery worker; the task's
`HelperConstraint` is raised to `ram_peak_mb=512`, `cpu_intensive=True`.

## 5 · Settings (default-on)

| Key | Default | Meaning |
|---|---|---|
| `spike_detection.history_days` | 90 | days of history Prophet fits |
| `spike_detection.noise_floor_clicks` | 10 | ignore pages below this on the target day |
| `spike_detection.upper_bound_factor` | 1.2 | actual must exceed the forecast ceiling by 20% |
| `spike_detection.prophet_max_items` | 200 | cap on per-page fits per run |
| `spike_detection.min_active_days` | 14 | skip pages with too few active days |

## 6 · One-way replacement

The flat 4×-average path is deleted in the same change: the
`_snapshot_gsc_clicks` Parquet export and the `_query_spikes` DataFusion pass
are removed. The GSC history is now pulled through ADBC inside `_load_history`
(so the Arrow-native read path stays in use), and DataFusion remains in use for
the analytics dashboard breakdowns (FR — telemetry rollups). The alert payload
key `avg_clicks` becomes `expected_upper`; no other code read it.

## 7 · References

- Taylor SJ, Letham B (2018), "Forecasting at scale", The American Statistician 72(1) — doi:10.7287/peerj.preprints.3190v2
- Prophet documentation — https://facebook.github.io/prophet/
