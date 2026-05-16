# Module: operations

**Layer:** 3 (orchestration).
**Status:** Stub — full detail lands in slice 9.
**Maps to today:** Celery jobs registry, Celery beat schedules, websocket layer, jobs dashboard, paper-trail surface, AutoIssue picker, performance baselines, the "ops console" pages.

## Plain-English summary

The operations module is the orchestration layer. It schedules Celery jobs, runs the Celery beat cron, pushes websocket updates, exposes the jobs dashboard, owns the paper-trail surface, owns the AutoIssue picker, and owns the performance-baseline tables. Anything that an operator interacts with through the ops console belongs here.

If a function is about scheduling, monitoring, or operator dashboards, it belongs here.

## Public interface

`operations.api` exports the orchestration verbs and the dashboards' read shapes. Examples slated for slice 9:

- `schedule_job(name: str, when: datetime)`
- `cancel_job(job_id: int)`
- `JobsDashboardSnapshot` (typed record for the Angular dashboard)
- `record_perf_baseline(function: str, ns: int)` (used by the slice-2 perf-proof gate)
- `pick_autoissues_for_session() -> list[AutoIssue]`
- `pick_paper_trail_for_session() -> list[PaperTrailEntry]`

Celery worker internals are private. The Celery beat schedule is private. Only the verbs and the dashboard shapes cross the boundary.

## Job (the "and"-test)

Operations owns one job: **scheduling, monitoring, and the operator surface.** It does not own business decisions (those live in `pipeline`, `suggestions`, `analytics`, `graph`) and it does not own the rules themselves (those live in `governance`).

## Owned tables

- Celery `result` and `task` tables (per the Celery convention)
- `JobsDashboardEntry`
- `PerfBaseline`, `PerfRun`
- `AutoIssue`, `AutoIssueLesson` (the AutoIssue queue tables today live in `apps/auto_issues/`; slice 9 moves them here)
- `PaperTrailEntry`, `PaperTrailHistory`

The full list arrives with the slice-9 move.

## Dependencies

- `platform` (audit logging, feature flags)
- `content`, `sources`, `pipeline`, `suggestions`, `analytics`, `graph` (read-only, through each module's `api.py`, for dashboard rendering)

Operations may import from any Layer-2 or Layer-1 module. No Layer-3 module imports from `operations`.

## Open questions

- The AutoIssue table is referenced by the pre-commit hooks (which live in `.githooks/`, outside the backend). Confirm the hook reads `operations.api` rather than reaching directly into the table.
- The websocket layer (Django Channels) bridges between `operations` and the Angular frontend. Slice 9 confirms the channel definitions are public in `operations.api`.

## Citations

- ISO/IEC/IEEE 42010:2022 — separation of orchestration concerns from business concerns at the architecture level.
- US8645233B2 — module-dependency enforcement at the orchestration boundary.

## Slice that moves this module

Slice 9 (with `governance`). Lands last among the business slices because it reads from every Layer-2 module.
