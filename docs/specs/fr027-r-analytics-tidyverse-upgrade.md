# FR-027 - CANCELLED: R Analytics Tidyverse Upgrade

## Status

**CANCELLED** — 2026-04-01 (analytics work superseded by Python after a brief 2026-Q1 C# detour; see "Second-wave update" below)

The R analytics service (`services/r-analytics/`) has been removed from the stack.

### Second-wave update (2026-04-12)

The interim C# Analytics Worker that originally replaced R was itself decommissioned.
Analytics now run **in-process inside the Python Celery worker** (`backend/apps/analytics/`)
using numpy / scipy / scipy.stats, and the Django ORM for batch reads and writes. The
historical replacement table below is preserved as a record of the two-step retirement.

## Why cancelled

FR-027 planned to upgrade the R service with four Tidyverse packages. Those goals are
now fully covered by Python and D3.js, with lower resource use and no R runtime dependency.

| FR-027 goal | Replacement (current — 2026-04) | Interim 2026-Q1 (decommissioned) |
|---|---|---|
| `dplyr` / `tidyr` — data manipulation, reshaping, gap-filling | pandas / numpy / Django ORM `Q`, `F`, `Case` | C# LINQ |
| `lubridate` — date arithmetic, rolling windows | `datetime` + `django.utils.timezone` + `pandas.Timedelta` | C# `DateOnly`, `TimeSpan`, `DateTime` |
| `ggplot2` — score distribution, traffic trend, scatter charts | D3.js in Angular frontend | D3.js in Angular frontend |
| `purrr::pwalk()` — batch writes replacing row-by-row loop | Django ORM `bulk_update` / `bulk_create` | Npgsql batch `UPDATE` via `UNNEST` |
| Shiny dashboard | Angular analytics page (FR-016 charts) | Angular analytics page (FR-016 charts) |
| FR-023 Hot decay scaffold | `backend/apps/analytics/services/` (Celery tasks) | C# `HttpWorker.Analytics` service |
| FR-024 rolling engagement scaffold | `backend/apps/analytics/services/` (Celery tasks) | C# `HttpWorker.Analytics` service |

## What replaced it

- **Python analytics layer** at `backend/apps/analytics/` (current)
  - `pandas` / `numpy` for aggregation, `scipy.stats` for confidence bounds and Wilson score
  - `scipy.optimize.minimize(method="L-BFGS-B")` for FR-018 weight optimization (see `backend/apps/suggestions/services/weight_tuner.py`)
  - Django ORM for direct PostgreSQL reads and `bulk_update` / `bulk_create` for writes
  - Runs as standard Celery tasks dispatched from `backend/apps/pipeline/tasks.py`
- **D3.js** in the Angular frontend for all charts defined in FR-016

## What was removed from the repo

- `services/r-analytics/` directory deleted in full (2026-Q1)
- `services/http-worker/` directory deleted (2026-04-12).
- Docker compose R-analytics service block removed (along with the whole override file in a later retirement pass)
- `AI-CONTEXT.md` tech stack updated through both retirement waves
- `FEATURE-REQUESTS.md` FR-022 health card 5 updated, FR-027 marked cancelled
- `docs/specs/fr018-auto-tuned-ranking-weights.md` rewritten 2026-04-26 to describe the live Python tuner (originally documented R loop, then C# loop)
- `docs/specs/fr021-graph-based-link-candidate-generation.md` references updated through both waves
- `docs/specs/fr022-data-source-system-health-check.md` health card 5 replaced (Python analytics) and card 11 marked decommissioned
