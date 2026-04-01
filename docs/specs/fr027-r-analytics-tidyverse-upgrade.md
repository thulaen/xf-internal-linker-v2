# FR-027 - CANCELLED: R Analytics Tidyverse Upgrade

## Status

**CANCELLED** — 2026-04-01

The R analytics service (`services/r-analytics/`) has been removed from the stack.

## Why cancelled

FR-027 planned to upgrade the R service with four Tidyverse packages. Those goals are
now fully covered by C# and D3.js, with lower resource use and no R runtime dependency.

| FR-027 goal | Replacement |
|---|---|
| `dplyr` / `tidyr` — data manipulation, reshaping, gap-filling | C# LINQ (built-in, no packages) |
| `lubridate` — date arithmetic, rolling windows | C# `DateOnly`, `TimeSpan`, `DateTime` |
| `ggplot2` — score distribution, traffic trend, scatter charts | D3.js in Angular frontend |
| `purrr::pwalk()` — batch writes replacing row-by-row loop | Npgsql batch `UPDATE` via `UNNEST` |
| Shiny dashboard | Angular analytics page (FR-016 charts) |
| FR-023 Hot decay scaffold | C# `HttpWorker.Analytics` service |
| FR-024 rolling engagement scaffold | C# `HttpWorker.Analytics` service |

## What replaced it

- **C# Analytics Worker** at `services/http-worker/src/HttpWorker.Analytics/`
  - LINQ for all data aggregation
  - `MathNet.Numerics` NuGet for Wilson score, confidence bounds, L-BFGS optimization (FR-018)
  - Npgsql for direct PostgreSQL reads and batch writes
  - Runs as a .NET `BackgroundService` inside `http-worker-api`

- **D3.js** in the Angular frontend for all charts defined in FR-016

## What was removed from the repo

- `services/r-analytics/` directory deleted in full
- `docker-compose.override.yml` R service block removed
- `AI-CONTEXT.md` tech stack updated
- `FEATURE-REQUESTS.md` FR-022 health card 5 updated, FR-027 marked cancelled
- `docs/specs/fr018-auto-tuned-ranking-weights.md` R loop replaced with C# loop
- `docs/specs/fr021-graph-based-link-candidate-generation.md` R references replaced
- `docs/specs/fr022-data-source-system-health-check.md` health card 5 replaced
