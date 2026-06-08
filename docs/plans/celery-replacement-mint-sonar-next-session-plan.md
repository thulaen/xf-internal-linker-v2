# Celery Replacement, Mint Quality Move, and Sonar Repair Plan

> **SUPERSEDED in part — language model changed 2026-06-06.** This plan proposes
> replacing Celery with a **Go** task runtime and repeatedly refers to keeping
> existing **Go sidecars**. The backend is now **Python + Rust only** (see
> [ADR 0007](../adr/0007-python-rust-two-language.md) and
> [`RUST-FIRST.md`](../../RUST-FIRST.md)); Go, Haskell, C++, and Lua are removed,
> and there is no Go services tier. Do **not** add a Go task runtime or new Go
> sidecars from this plan. Harvest only the language-neutral ideas (the Redis
> Streams task model, the Mint quality/observability move, and the Sonar repair);
> any new task-runtime or hot-path work must be Python orchestration plus a Rust
> extension on the hot path, with no Python fallback. The Mint-move and Sonar
> portions remain useful.

Last refreshed: 2026-05-26.

Audience: the next Codex, Claude, Gemini, or other repo agent that receives a fresh session after this long one becomes too heavy.

Plain-English glossary for this plan:

- Celery means the current Python background task system. It runs scheduled jobs, queue workers, retries, and long work outside the web request.
- Celery Beat means the current scheduler that wakes up and sends periodic Celery tasks.
- Redis means the in-memory service already used here for fast queue and lock data.
- Redis Streams means a Redis data type that stores ordered events and supports worker groups, acknowledgements, and pending work.
- Go means the compiled language we will use for the new low-memory task runner.
- Task runner means the replacement for Celery workers and Celery Beat.
- Worker means a long-running process that takes a queued job and runs it.
- Scheduler means the process that decides when periodic jobs are due.
- BDD means behavior-driven description using Given, When, Then.
- TDD means test-driven development: write or update the focused test before or alongside the code, run it, make it pass, and keep it passing.
- Mutation testing means deliberately changing small pieces of code to prove tests catch wrong behavior.
- Profiling means measuring where time and memory are actually spent.
- SonarQube means the local code-quality scanner server.
- SonarScanner means the command-line program that sends the repo to SonarQube for analysis.
- Mint means the Linux helper machine on the private cable address `10.10.10.91`.
- Windows control plane means the laptop services that must stay local because they hold the live agent session, database writer, credentials, hooks, and user-facing development loop.

## One-Sentence Goal

Replace the repo's Celery workers and Celery Beat scheduler with a smaller Go task runtime, prove the new runtime uses at most one fifth of the current Celery memory and makes task-runner overhead at least 20 times faster, move the requested quality and observability tools to Mint except existing Go sidecars, repair Sonar scanning, and leave no hidden fallback, duplicate scheduler, silent disabled service, or unverified benchmark behind.

## Current Evidence Read In This Session

The next session must re-run the normal session ritual, but this plan is based on the following repo evidence already inspected on 2026-05-26:

- `AGENT-HANDOFF.md` latest entry says Windows Docker stopped and removed moved-service GlitchTip containers and images, protected named volumes were left untouched, and no commit happened.
- `print_open_issues` reported 1,940 open issues: 205 agent, 118 GlitchTip, 40 Pyroscope, 26 Tempo, 74 Loki, 6 Faro, 116 mutation, 0 fuzz, 0 contract, 2 GitHub Actions continuous-integration failures, 996 SonarQube, 74 vmalert, and 282 Rust defect.
- `print_open_paper_trail` reported 3 open paper-trail entries: one debt-reduction, one tooling-gap, and one documentation entry.
- `print_open_snapshots` reported no open issue snapshots.
- `read_sticky --id 1` reported sticky hash `7b8d04510bf49e49`.
- `print_failed_github_actions --since-handoff` reported 0 failures since the latest handoff.
- `check_observability_health` reported degraded signals for `alloy`, `grafana`, `loki`, `otel-collector`, `postgres-exporter`, `pyroscope`, `sonar-autoscan`, `sonarqube`, `tempo`, `vmagent`, `vmalert`, and `vmsingle`.
- `backend/config/celery.py` configures one Celery app, three queues (`default`, `pipeline`, `embeddings`), worker-startup catch-up, and a fork-safety database-close signal.
- `backend/config/settings/base.py` enables `django_celery_beat`, `django_celery_results`, Redis as Celery broker, Django database as Celery result backend, JSON serializers, UTC time, queue routes, and Celery instrumentation.
- `docker-compose.yml` still defines `celery-worker-default`, `celery-worker-pipeline`, and `celery-beat`.
- `backend/config/settings/celery_schedules.py` contains the live Celery Beat schedule for imports, tuning, scorecards, pickers, SonarQube ingest, retention jobs, health jobs, and other automation.
- `backend/config/catchup_registry.py` maps many Beat jobs to startup catch-up rules.
- `backend/apps/scheduled_updates/runner.py` already contains a serial job runner with Redis locks, pause behavior, progress checkpoints, WebSocket broadcasts, missed-job handling, and alerting. That domain logic should be reused, not rewritten.
- A repo-wide search found many `@shared_task` task definitions in `analytics`, `content`, `cooccurrence`, `benchmarks`, `audit`, `crawler`, `core`, `notifications`, `health`, `auto_issues`, `scheduled_updates`, `work_queue`, `pipeline`, and `suggestions`.
- `backend/apps/work_queue/` exists but is not the replacement task runner yet. Its current public API is for agent claims, repair attempts, feed projection, self-healing decisions, and historical fix suggestions.
- `config/observability-services.json` still calls itself the Windows source of truth and still lists services now intended for Mint, which explains current false "absent" findings.
- `scripts/start-mint-quality-tools.ps1` already creates a Mint-only `.env.mint-quality`, can generate a Sonar token from local admin credentials, starts `compiled-tools`, `sonarqube`, `sonar-autoscan`, `pyroscope`, `pyroscope-ebpf-profiler`, and `multi-lang-observability-picker`, and stops Windows copies unless told not to.
- `scripts/check-mint-quality-tools.ps1` already fails when `SONAR_TOKEN` is missing or when recent `sonar-autoscan` logs contain HTTP 401.
- `docker-compose.yml` already points backend and Celery containers at `SONAR_HOST_URL=http://10.10.10.91:9000`, but the scanner and autoscan service blocks still contain local `http://sonarqube:9000` defaults and local `depends_on` wiring.
- `backend/apps/auto_issues/tasks.py` contains `auto_issues.ingest_sonarqube_findings`, currently a Celery task that reads `SONAR_HOST_URL` defaulting to `http://sonarqube:9000` and skips if `SONAR_TOKEN` is missing.
- `docs/specs/fr-mint-quality-tool-placement.md` says Mint owns compiled tools, Haskell quality, SonarQube, and sonar-autoscan, while Windows keeps Django, Redis, Postgres, Celery, Lua advisor, hooks, sessions, credentials, AutoIssue, and PaperTrail. This spec must be revised during the Celery replacement because Windows will no longer keep Celery after the final cutover.

## Official Source Backbone

These are the source documents the implementation specs must cite. If a URL moves, the next session must refresh the spec citation before code:

- Celery periodic tasks and Beat behavior: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
- Celery task retry and late acknowledgement behavior: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- Redis Streams and consumer groups: https://redis.io/docs/latest/develop/data-types/streams/
- Redis `XREADGROUP` command: https://redis.io/docs/latest/commands/xreadgroup/
- Go HTTP pprof package: https://go.dev/pkg/net/http/pprof/
- Go runtime pprof package: https://go.dev/pkg/runtime/pprof/
- Docker Compose profiles and service lifecycle: https://docs.docker.com/reference/cli/docker/compose/
- OpenTelemetry Collector exporters and collector configuration: https://opentelemetry.io/docs/collector/components/exporter/
- SonarQube scanner parameters, including `SONAR_TOKEN` and `SONAR_HOST_URL`: https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/analysis-parameters/parameters-not-settable-in-ui
- SonarQube token management: https://docs.sonarsource.com/sonarqube-server/latest/user-guide/managing-tokens/
- SonarQube Docker guidance: https://docs.sonarsource.com/sonarqube-server/2025.3/setup-and-upgrade/install-the-server-as-a-cluster/

The plan intentionally uses official docs or already-inspected local specs. Do not replace these citations with blog posts unless an official source is missing and the paper-trail entry explains why.

## Non-Negotiable Boundaries

Given this repository uses strict paper-trail, source-backed specs, and no-silent-disablement rules,
When the next session starts implementation,
Then the agent must create or update the required specs before source code, write BDD scenarios in Given/When/Then form, write tests before or alongside code, run real commands, and only claim markers that the actual work proves.

Given the user asked to move requested build and observability work to Mint but not Go sidecars,
When services are moved,
Then existing Go sidecars stay out of this move plan, and the Mint move only covers the requested quality and observability services: compiled tools, Haskell quality, SonarQube, Sonar autoscan, Loki, Tempo, VictoriaMetrics services, vmagent, vmalert, Alloy, OpenTelemetry collector, Pyroscope, Grafana, postgres-exporter, and already-moved GlitchTip style services if still present.

Given Windows is the live control plane,
When Celery is replaced,
Then Windows keeps the Django backend, Postgres primary data, Redis, frontend dev and test loop, hooks, session lookup, AutoIssue writer, PaperTrail access, provider credentials, and agent-control services. Celery remains only until its owned tasks have one-way migrations. Converted tasks must not keep a Celery fallback.

Given no protected data may be deleted,
When cleaning Docker or moving services,
Then do not run `docker volume prune`, do not run `docker compose down -v`, do not delete named database or observability volumes, and do not delete local secrets. Safe cleanup is limited to stopped containers, dangling images, and build cache after before-and-after evidence.

Given the benchmark target is aggressive,
When the task runner replacement is evaluated,
Then the final replacement must prove both memory and speed: at most 20 percent of current Celery runtime memory for equivalent queues, and at least 20 times faster task-runner overhead. The term overhead means enqueue, due-schedule decision, claim, acknowledgement, retry bookkeeping, progress event write, and result bookkeeping. If a job is slow because it waits on an external website or SonarQube, the external wait is measured separately and cannot be counted as a runner failure, but the plan still must prove the runner's own work is 20 times faster.

Given Celery currently runs real production work,
When migrating,
Then each task family moves in a one-way slice: tests first, code second, old Celery route removed for that task family third, and verification last. During the multi-session migration, Celery may remain for tasks not yet migrated, but a migrated task must have exactly one live runner.

## High-Level Target Architecture

The target is a small Go task runtime plus a thin Python task API.

The Go runtime has four processes or subcommands:

1. `taskrunner scheduler`: reads the schedule registry and enqueues due jobs.
2. `taskrunner worker --queue default`: handles light background work.
3. `taskrunner worker --queue pipeline`: handles long pipeline work with strict concurrency and memory limits.
4. `taskrunner janitor`: retries expired leases, trims completed queue entries, files dead-letter AutoIssues, and writes health rows.

The Python side has these pieces:

1. `backend/apps/operations/task_runtime/api.py`: the public Django API for enqueueing, canceling, and reading job state.
2. `backend/apps/operations/task_runtime/models.py`: a small job ledger and schedule ledger, unless the implementation proves existing models can be reused cleanly.
3. `backend/apps/operations/task_runtime/registry.py`: the task registry generated from or replacing current `@shared_task` declarations.
4. `backend/apps/operations/task_runtime/dispatcher.py`: thin code that writes task envelopes to Redis Streams and job rows.
5. A management command that can run one task by name in-process for tests and emergency repair, but not as a hidden fallback in production.

The queue substrate is Redis Streams plus a small delayed-job sorted set:

- Redis Streams hold ready jobs because Streams support append-only events, consumer groups, pending entries, acknowledgement, and trimming.
- A Redis sorted set holds jobs whose `run_at` time is in the future. The scheduler moves due jobs into the stream.
- Postgres holds durable job metadata, human-readable status, cancellation state, and audit information.
- The Redis stream is trimmed by a count and age rule so it cannot grow forever.
- The job ledger stores enough data to restart safely after Redis restart, but large payloads stay in domain tables or files, not in the queue message.

The task envelope has a stable schema:

- `task_id`: globally unique job id.
- `task_name`: stable plain string, for example `auto_issues.ingest_sonarqube_findings`.
- `queue`: `default`, `pipeline`, `embeddings`, or a new queue approved by spec.
- `args_ref`: pointer to durable inputs, not a huge JSON blob.
- `kwargs`: small JSON object for scalar options only.
- `idempotency_key`: stable dedup key for repeat-safe tasks.
- `trace_id`: OpenTelemetry trace id if one exists.
- `created_by`: user, agent, or scheduler identity.
- `run_at`: due time.
- `attempt`: current attempt.
- `max_attempts`: retry ceiling.
- `timeout_seconds`: hard task budget.
- `lease_seconds`: claim expiry window.
- `priority`: simple integer priority.
- `schema_version`: envelope schema version.

The Go worker never imports Django code. It calls a small set of stable entrypoints:

- For Python-owned domain work, the Go worker invokes `python manage.py run_task_runtime_job --task-id <id>` inside the backend container or a dedicated backend-runner container. This is an interim bridge only for Python-owned domain logic.
- For task-runner-owned bookkeeping, Go talks directly to Redis and writes status through a narrow HTTP or management-command ingestion endpoint.
- For future CPU-heavy routines, Go can call C ABI libraries or Go-native implementations, but only after profiling proves the need.

This split is deliberate. The first goal is to replace Celery's high-memory worker machinery and scheduler behavior without rewriting every business function at once. The later goal is to move individual hot jobs into Go or native code only when profiling proves it is worth the extra boundary.

## Memory and Performance Contract

Given current documentation in `docs/PERFORMANCE.md` lists `celery-worker-default` around 1.5 GB, `celery-worker-pipeline` around 2 GB, and `celery-beat` around 128 MB,
When the baseline slice starts,
Then the agent must measure the real current numbers on this machine before editing code.

The required baseline command set is:

1. `docker --context desktop-linux compose ps celery-worker-default celery-worker-pipeline celery-beat`
2. `docker --context desktop-linux stats --no-stream xf_linker_celery_worker_default xf_linker_celery_worker_pipeline xf_linker_celery_beat`
3. `docker --context desktop-linux exec xf_linker_celery_worker_default ps -o pid,rss,comm,args`
4. `docker --context desktop-linux exec xf_linker_celery_worker_pipeline ps -o pid,rss,comm,args`
5. `docker --context desktop-linux exec xf_linker_celery_beat ps -o pid,rss,comm,args`
6. `docker --context desktop-linux exec xf_linker_celery_worker_pipeline du -sh /tmp`
7. `docker --context desktop-linux exec xf_linker_celery_beat du -sh /tmp`
8. `docker --context desktop-linux compose exec -T backend python manage.py inspect_profiles --service celery --scope backend/apps,backend/config`
9. `docker --context desktop-linux compose exec -T backend python manage.py check_observability_health`

The required performance baseline command set is:

1. A new benchmark command `manage.py benchmark_task_runtime --backend celery --fixture smoke_1000`.
2. A new benchmark command `manage.py benchmark_task_runtime --backend celery --fixture delayed_10000`.
3. A new benchmark command `manage.py benchmark_task_runtime --backend celery --fixture retries_1000`.
4. A new benchmark command `manage.py benchmark_task_runtime --backend celery --fixture schedule_jitter_1440`.
5. A new benchmark command `manage.py benchmark_task_runtime --backend celery --fixture progress_events_1000`.

The replacement can only be called complete after matching Go-backed commands exist:

1. `manage.py benchmark_task_runtime --backend go --fixture smoke_1000`
2. `manage.py benchmark_task_runtime --backend go --fixture delayed_10000`
3. `manage.py benchmark_task_runtime --backend go --fixture retries_1000`
4. `manage.py benchmark_task_runtime --backend go --fixture schedule_jitter_1440`
5. `manage.py benchmark_task_runtime --backend go --fixture progress_events_1000`

The final gate is:

- Memory: `taskrunner scheduler + all taskrunner workers + any bridge process needed for equivalent migrated queues` uses no more than 20 percent of `celery-worker-default + celery-worker-pipeline + celery-beat` resident memory under the same fixture load.
- Speed: p50 and p95 task-runner overhead are at least 20 times better for enqueue-to-claim, schedule due-to-enqueue, claim-to-start, acknowledgement, retry bookkeeping, and progress event write.
- Disk: `/tmp` growth from task-runner processes remains below 100 MB after the 60-minute soak.
- Stability: no stuck pending jobs, no duplicate successful jobs for the same idempotency key, no unacknowledged job older than its retry window, and no silent skip.

If the first implementation only reaches half-memory but not one-fifth memory, that is not done. It is an interim checkpoint. The next session must keep iterating with profiling evidence until it reaches the 5x memory reduction. If the first implementation reaches 8x or 10x memory reduction, record that in the proof and keep the stricter result as the new floor.

## Specs To Create Or Update Before Code

The next implementation session must create or update these source-backed specs before source changes:

1. `docs/specs/fr-celery-replacement-task-runtime.md`
   - Covers why Celery is being replaced, what behavior must remain, task envelope schema, Redis Streams design, delayed-job design, retry semantics, cancellation, idempotency, and final Celery removal.
   - Citations: Celery tasks docs, Celery periodic tasks docs, Redis Streams docs, Redis `XREADGROUP` docs, Beck TDD book or existing TDD spec.

2. `docs/specs/fr-task-runtime-benchmark-proof.md`
   - Covers baseline commands, benchmark fixtures, memory targets, speed targets, soak tests, mutation tests, and profiling proof.
   - Citations: Go pprof docs, OpenTelemetry docs, Pyroscope local spec if present, Docker stats docs if a current local spec cites it.

3. `docs/specs/fr-task-runtime-schedule-catchup.md`
   - Covers replacement of Celery Beat, `django_celery_beat`, and `config/catchup_registry.py`.
   - Citations: Celery Beat official docs and a source on cron semantics already used in repo specs or official library docs.

4. `docs/specs/fr-task-runtime-migration-inventory.md`
   - Lists every current Celery task by module, queue, schedule, timeout, retry shape, idempotency key, side effects, ownership module, tests, and migration slice.
   - This can be generated partly by a command, but the spec is the human source of truth during migration.

5. `docs/specs/fr-mint-quality-observability-placement.md`
   - Updates the existing Mint quality placement spec so it no longer says Windows keeps Celery after final cutover.
   - Defines which quality and observability services run on Mint, which stay on Windows, and why existing Go sidecars are excluded.

6. `docs/specs/fr-remote-observability-health.md`
   - Replaces the current Windows-only `config/observability-services.json` assumption with a location-aware service catalog.
   - Defines how health checks query local Docker, Mint Docker, and HTTP readiness endpoints.

7. `docs/specs/fr-sonar-autoscan-token-bootstrap.md`
   - Covers Sonar token generation, storage, validation, refresh, HTTP 401 handling, scanner success markers, AutoIssue filing, and no tracked secrets.
   - Citations: SonarQube token docs, SonarQube scanner parameter docs, SonarQube Docker docs.

8. `docs/specs/fr-celery-final-removal.md`
   - Covers removal of `celery`, `django_celery_beat`, `django_celery_results`, `config/celery.py`, Compose services, instrumentation, health checks, and user-facing wording.
   - Explains which historical Celery database tables remain read-only for retention and which later migration may archive them.

Each spec must carry `[SPEC FRESHNESS: reviewed_at=2026-05-26 next_review=2026-06-26]` or a later current-month date. If the next session starts in a later month, update the dates before code.

## Phase 0 - Session Start And Safety Lock

Given this work changes the backbone of background jobs,
When a fresh session begins,
Then the agent must run the full repo ritual before any plan or code, including handoff, open issues, failed GitHub Actions runs, guidelines, quality gate, paper trail, snapshots, sticky 1, scoped lessons, lessons before start, and test-driven-development preflight.

Given the worktree is already dirty,
When the next agent starts,
Then it must inspect `git status --short`, identify unrelated existing changes, and avoid reverting user or prior-agent work.

Given this plan is intended to be copy-pasted into a new session,
When the next agent begins,
Then it should read this file, then read the specs named above, then read the current Celery files:

- `backend/config/celery.py`
- `backend/config/settings/base.py`
- `backend/config/settings/celery_schedules.py`
- `backend/config/catchup_registry.py`
- `docker-compose.yml`
- `backend/apps/scheduled_updates/runner.py`
- `backend/apps/auto_issues/tasks.py`
- `backend/apps/work_queue/api.py`
- `backend/apps/work_queue/models.py`
- `backend/apps/observability/management/commands/check_observability_health.py`
- `config/observability-services.json`
- `scripts/start-mint-quality-tools.ps1`
- `scripts/check-mint-quality-tools.ps1`

Given this repo has a modular monolith rule,
When adding the task runtime,
Then the public surface must live under the operations module or the existing module map must be updated in the spec. Cross-module Python imports must go through `api.py`. The default decision is that the operations module owns the task runtime because `docs/modules/operations.md` already maps background jobs, schedules, websockets, job dashboards, paper trail, AutoIssue picker, and performance baselines to operations.

## Phase 1 - Full Celery Inventory

Given a replacement cannot be correct unless every current Celery behavior is known,
When Phase 1 starts,
Then create a generated inventory command before editing any task implementation.

Add a command named:

`docker --context desktop-linux compose exec -T backend python manage.py inventory_celery_tasks --format markdown --output /repo/tmp/celery-task-inventory.md`

The command must read:

- `app.tasks` from the Celery app.
- `CELERY_BEAT_SCHEDULE`.
- `CELERY_TASK_ROUTES`.
- `config/catchup_registry.py`.
- task decorators and explicit names from `backend/apps/**/tasks*.py`.
- `.delay`, `.apply_async`, `AsyncResult`, and revoke call sites.

The output must contain one row per task:

- Task name.
- Python file.
- Owning module.
- Queue.
- Schedule, if any.
- Timeout or expected duration.
- Retry policy.
- Idempotency key proposal.
- Side effects.
- External services touched.
- Whether it can run during global pause.
- Whether it can run during maintenance mode.
- Migration slice.
- Required regression test.

BDD acceptance:

Given the repo contains `auto_issues.ingest_sonarqube_findings`,
When the inventory command runs,
Then the output lists it as a scheduled SonarQube ingest task, notes its `SONAR_HOST_URL` and `SONAR_TOKEN` dependency, and marks it blocked until Sonar token validation is fixed.

Given the repo contains `scheduled_updates.run_next_scheduled_job`,
When the inventory command runs,
Then the output lists it as a serial orchestrator task and points to `backend/apps/scheduled_updates/runner.py` as reusable domain logic.

Given the repo contains pipeline embedding tasks,
When the inventory command runs,
Then the output marks them as heavy, queue-limited, and requiring explicit memory and profile gates before migration.

Given the repo contains task call sites using `.delay` or `.apply_async`,
When the inventory command runs,
Then each call site is listed with file and line number so the migration can remove Celery calls rather than leaving dead wrappers.

Test-first requirements:

- Add `backend/config/tests/test_celery_inventory.py`.
- Test that the command discovers at least one task from each touched module.
- Test that `CELERY_BEAT_SCHEDULE` entries appear in the output.
- Test that queue routes are reflected correctly.
- Test that `.delay` and `.apply_async` call sites are reported.
- Test that the command fails loudly if `config/celery.py` cannot import.

Do not start code migration until this inventory exists and passes tests.

## Phase 2 - Baseline Celery Memory, Disk, And Speed

Given the user wants 5x less RAM and 20x more performance,
When Phase 2 starts,
Then build the measurement harness before building the replacement.

Add a benchmark command:

`manage.py benchmark_task_runtime --backend celery --fixture <fixture> --output tmp/task-runtime-benchmarks/<timestamp>.json`

Fixtures:

1. `smoke_1000`: 1,000 tiny no-op jobs.
2. `payload_1000`: 1,000 jobs with small JSON payloads.
3. `delayed_10000`: 10,000 scheduled future jobs.
4. `retries_1000`: 1,000 jobs that fail once then succeed.
5. `timeouts_100`: 100 jobs that exceed timeout and must be marked failed.
6. `schedule_jitter_1440`: a simulated day of minutely scheduler ticks.
7. `progress_events_1000`: 1,000 jobs that emit 10 progress events each.
8. `sonar_ingest_mock`: a SonarQube ingest run against mocked Sonar API pages.
9. `scheduled_updates_mock`: a scheduled-updates run using fake registry entries.

The command must measure:

- Enqueue p50, p95, p99.
- Time from due schedule to queued.
- Time from queued to worker claim.
- Time from worker claim to user code start.
- Acknowledgement latency.
- Retry latency.
- Scheduler jitter.
- Completed jobs per second.
- Duplicate completion count.
- Lost job count.
- Resident memory before, during, and after.
- `/tmp` growth.
- Redis memory used by broker keys.
- Postgres writes per job.

BDD acceptance:

Given the Celery backend is selected,
When `smoke_1000` runs,
Then the command records Celery metrics and writes a JSON file with all required fields.

Given a fixture cannot run because a service is down,
When the benchmark command runs,
Then it fails clearly, files or updates an AutoIssue if appropriate, and does not write a fake success record.

Given the profiler pipeline is degraded,
When the benchmark command runs,
Then it records the missing profile source and points to the profiling pipeline AutoIssue instead of inventing profiling proof.

Test-first requirements:

- Add unit tests for benchmark result schema.
- Add tests for fake Celery backend so the command can be exercised without real Celery.
- Add tests that missing services produce a non-zero exit and clear message.
- Add a regression test that the command refuses to compare Celery and Go results if fixtures differ.

Mutation testing:

- Mutate comparison operators in the benchmark pass/fail decision.
- Mutate missing-field checks in the result schema.
- Mutate fixture names.
- The tests must fail when these mutants survive.

## Phase 3 - Task Envelope And Python Public API

Given Celery currently hides task arguments, retries, result state, and cancellation behind a library,
When replacing it,
Then define an explicit task envelope and a small public Python API.

Create `backend/apps/operations/task_runtime/` or the closest existing operations-owned path. If an operations app does not exist physically yet, create the smallest compliant app and update module docs. Do not put new cross-module task runtime code inside `apps.core` or `apps.auto_issues` just because those folders are nearby.

Public API functions:

- `enqueue_task(task_name, *, args_ref=None, kwargs=None, queue="default", run_at=None, idempotency_key=None, priority=100, timeout_seconds=None, max_attempts=None, created_by=None) -> TaskHandle`
- `cancel_task(task_id, reason, requested_by) -> CancelResult`
- `get_task_status(task_id) -> TaskStatus`
- `record_task_progress(task_id, percent=None, message="", payload=None) -> None`
- `register_task(TaskDefinition) -> None`
- `list_registered_tasks() -> list[TaskDefinition]`

The API must be boring and small. It should not expose Redis commands to callers. It should not take more than seven arguments in any one function. If a call needs more, use a dataclass.

Task definitions must include:

- Stable name.
- Owning module.
- Queue.
- Handler import path.
- Timeout.
- Retry policy.
- Whether idempotency is required.
- Pause behavior.
- Maintenance-mode behavior.
- Expected resource class: light, medium, heavy, external I/O, scanner, or schedule-only.

BDD acceptance:

Given a caller enqueues `auto_issues.ingest_sonarqube_findings` with the same idempotency key twice,
When both calls happen before the first job completes,
Then only one live job is created and the second call returns the existing handle.

Given a caller enqueues a task without a task definition,
When the API validates the name,
Then it raises a typed error and files no queue message.

Given maintenance mode is active and a task definition forbids writes,
When a caller enqueues that task,
Then the API returns a clear blocked result, not a silent skip.

Given global pause is active,
When a caller enqueues a task that is not allowed during pause,
Then the API marks it deferred and does not place it into the ready stream until resume.

Test-first requirements:

- Unit tests for envelope validation.
- Unit tests for idempotency.
- Unit tests for pause and maintenance behavior.
- Unit tests for scheduled future jobs.
- Unit tests for bad task names.
- Unit tests for schema version mismatch.
- Contract tests proving all cross-module callers import only through the operations public API.

Mutation testing:

- Mutate idempotency comparison.
- Mutate pause checks.
- Mutate maintenance checks.
- Mutate queue name validation.
- The tests must fail on these mutants.

## Phase 4 - Redis Streams Queue And Lease Semantics

Given Redis is already part of the Windows control plane,
When implementing the queue,
Then use Redis Streams for ready jobs and a Redis sorted set for delayed jobs, unless a benchmark proves another Redis primitive is better.

Redis keys:

- `xf:tasks:ready:<queue>` for each ready stream.
- `xf:tasks:delayed` for run-at scheduling.
- `xf:tasks:cancelled` for cancellation requests.
- `xf:tasks:dead` for dead-letter references.
- `xf:tasks:dedupe` for idempotency locks.
- `xf:tasks:metrics` for short-lived runtime counters.

Consumer groups:

- One consumer group per queue.
- Consumer name includes host, process id, and worker id.
- Workers claim with `XREADGROUP`.
- Workers acknowledge only after the handler finishes and status is durably recorded.
- The janitor checks pending entries and reclaims expired leases.
- Completed stream entries are trimmed by age and count.

BDD acceptance:

Given 1,000 ready jobs in `default`,
When two workers consume from the same consumer group,
Then each job is started once, completed once, and acknowledged once.

Given a worker dies after claiming a job but before acknowledging it,
When the lease expires,
Then the janitor requeues or reclaims the job and records the attempt.

Given a job exceeds maximum attempts,
When it fails again,
Then it moves to dead-letter state, files or updates an AutoIssue, and appears in the diagnostics view.

Given Redis contains old completed stream entries,
When trimming runs,
Then completed entries older than the retention window are removed without deleting pending or failed work.

Test-first requirements:

- Go unit tests with a Redis test container or miniredis equivalent if accepted by repo standards.
- Python contract tests for key names and envelope shape.
- Integration tests against the repo Redis container.
- Race test with multiple Go workers.
- Crash recovery test that simulates a worker process exit after claim.

Mutation testing:

- Use Go mutation tooling for claim, ack, retry, and max-attempt logic.
- Use Python mutation tooling for envelope writing and dedupe decisions.
- Any surviving mutant in claim or acknowledgement logic blocks final removal.

Performance notes:

- Batch Redis reads and acknowledgements where safe.
- Use Redis pipelining for job status updates where safe.
- Keep message payload small. Large payloads must be in Postgres domain rows or files.
- Avoid unbounded streams. Every stream needs trim configuration and tests.

## Phase 5 - Go Scheduler Replacing Celery Beat

Given `backend/config/settings/celery_schedules.py` is the current scheduler source,
When replacing Celery Beat,
Then introduce a scheduler registry that can be generated from the current schedule and then maintained directly.

The first version must support:

- Fixed interval schedules.
- Crontab schedules.
- Start and end windows.
- Queue selection.
- Task options.
- Missed-run catch-up.
- Pause behavior.
- Maintenance-mode behavior.
- Human-readable next-run explanation.

The scheduler stores state:

- Last scheduled time.
- Last actual enqueue time.
- Last success time.
- Last failure time.
- Next due time.
- Consecutive missed count.
- Consecutive failure count.
- Catch-up decision.

BDD acceptance:

Given `sonarqube-findings-ingest` is scheduled every 30 minutes,
When Sonar token validation is green,
Then the Go scheduler enqueues the ingest job at the expected cadence and records each due decision.

Given `sonarqube-findings-ingest` is scheduled but Sonar token validation is red,
When the scheduler reaches the due time,
Then it files or updates a visible AutoIssue and does not pretend the scan was green.

Given a daily job was missed while the scheduler was down,
When the scheduler starts,
Then it applies the catch-up rule from the replacement catch-up registry and either queues one catch-up job or records why catch-up is not allowed.

Given global pause is active,
When the scheduler ticks,
Then it records due jobs as deferred and does not enqueue them until resume.

Given maintenance mode is active,
When a write-heavy scheduled job becomes due,
Then it is deferred with a clear reason.

Test-first requirements:

- Unit tests for interval schedule calculation.
- Unit tests for crontab schedule calculation.
- Unit tests for catch-up decisions from current `catchup_registry.py`.
- Unit tests for global pause and maintenance mode.
- Regression tests for at least 10 existing schedule entries, including Sonar ingest, scheduled updates runner, nightly sync, and retention cleanup.
- Integration test that scheduler writes to Redis stream and job ledger.

Mutation testing:

- Mutate due-time comparisons.
- Mutate catch-up threshold.
- Mutate pause checks.
- Mutate queue selection.
- Tests must catch these changes.

Removal rule:

After the Go scheduler owns a schedule entry, remove that entry from `CELERY_BEAT_SCHEDULE`. Do not leave it in both schedulers.

## Phase 6 - Go Workers Replacing Celery Queues

Given the current Compose file has `celery-worker-default`, `celery-worker-pipeline`, and `celery-beat`,
When Go workers are introduced,
Then start with new services that do not claim any migrated task until the tests and schedule registry explicitly route that task to Go.

Compose services during migration:

- `taskrunner-scheduler`
- `taskrunner-worker-default`
- `taskrunner-worker-pipeline`
- `taskrunner-janitor`

Each service must have:

- Explicit memory limit.
- Explicit CPU limit if supported by the Compose pattern already used here.
- Health check that verifies process liveness and Redis reachability.
- pprof endpoint bound only to internal network or localhost.
- OpenTelemetry exporter configuration.
- Pyroscope or equivalent profile configuration if the repo profiler supports it.
- No access to Docker socket unless a spec proves it is needed.
- No direct write to protected volumes.

BDD acceptance:

Given `taskrunner-worker-default` starts,
When Redis is reachable,
Then health is healthy and the worker reports zero claimed jobs.

Given Redis is not reachable,
When the worker starts,
Then health is unhealthy and the worker exits or fails clearly.

Given the worker receives a Python-owned job,
When the bridge command returns success,
Then the worker records success, acknowledges the stream entry, and emits a progress event.

Given the bridge command returns failure,
When attempts remain,
Then the worker records failure, schedules retry, and does not acknowledge success.

Given a cancellation request arrives before user code starts,
When the worker sees the cancellation token,
Then it marks the job cancelled and never starts the handler.

Given a cancellation request arrives while user code runs,
When the handler reaches a cancellation checkpoint,
Then it exits cleanly and records cancelled.

Test-first requirements:

- Go unit tests for worker loop.
- Go unit tests for retry policy.
- Go unit tests for cancellation.
- Go unit tests for health endpoint.
- Go unit tests for pprof endpoint registration.
- Integration tests with Redis.
- Python tests for bridge management command.
- End-to-end test from Python API enqueue to Go worker completion.

Mutation testing:

- Mutate retry branch.
- Mutate cancellation branch.
- Mutate success acknowledgement.
- Mutate dead-letter threshold.
- Tests must catch every task-state mutant before Celery removal.

## Phase 7 - Python Bridge And Domain Handler Migration

Given most current task handlers are Python functions with Django model access,
When replacing Celery,
Then keep domain logic in Python at first and replace the task transport around it.

The bridge command:

`python manage.py run_task_runtime_job --task-id <id>`

It must:

- Load the task row.
- Validate task name against registry.
- Set trace context.
- Mark started.
- Call the registered Python handler.
- Catch known typed errors and map them to retryable or final failure.
- Refuse unknown task names.
- Respect cancellation checkpoints.
- Record final status.
- Return a clear exit code.

Handlers should be small wrappers around existing domain services. If a current Celery task contains business logic directly, the migration slice should extract that logic into a service function first, then register the service with the new task runtime. This is not a broad refactor license. Extract only what is needed to avoid duplicating logic between old and new entrypoints during the same slice.

BDD acceptance:

Given a current Celery task calls a service function,
When it is migrated,
Then the new task runtime calls the same service function and the Celery task wrapper is deleted for that task.

Given a current Celery task contains inline logic,
When it is migrated,
Then the logic is extracted once into the owning module's service layer and both tests prove the service behavior, after which the Celery wrapper is removed.

Given a task still has a Celery wrapper after migration,
When the migration test runs,
Then it fails and tells the agent which task name still has dual routing.

Test-first requirements:

- A static test that every migrated task name is absent from Celery app task registry.
- A static test that no migrated task call site uses `.delay` or `.apply_async`.
- A service-level regression test per migrated task family.
- An end-to-end enqueue and completion test per migrated task family.

Mutation testing:

- Mutate handler mapping.
- Mutate typed error mapping.
- Mutate migrated-task static allowlist.
- Tests must fail.

## Phase 8 - First Task Families To Migrate

The migration order should reduce risk and memory pressure quickly.

### Task-Family Acceptance Matrix

This matrix is the guardrail against replacing only the easy part of Celery. The next session must keep expanding it from the generated inventory until every task family has a row. A row is complete only when it names the owner module, task names, current Celery queue, new runtime queue, schedule source, idempotency rule, cancellation rule, retry rule, test command, mutation command, and benchmark fixture.

Given a task family is missing from this matrix,
When the agent tries to migrate it,
Then the migration stops and the inventory/spec row is added first.

Given a task family is marked migrated,
When the absence tests run,
Then no task in that family remains in the Celery registry and no caller still uses `.delay` or `.apply_async`.

1. SonarQube ingest and quality scanner work:
   - Owner module: governance or operations, depending on where the source-backed spec places scanner ingestion after review.
   - Current task examples: `auto_issues.ingest_sonarqube_findings`.
   - New queue: `default` unless profiling proves scanner ingestion needs its own queue.
   - Idempotency key: `sonarqube:<project-key>:<scanner-run-id-or-analysis-date>`.
   - Cancellation: safe before API paging starts; after paging starts, finish the current page and stop before the next page.
   - Retry: retry on temporary network failure, do not retry blindly on HTTP 401 or HTTP 403.
   - Required proof: mocked API page tests, live Mint token validation, and one successful autoscan marker.

2. AutoIssue source pickers:
   - Owner module: governance or operations through public API.
   - Current task examples: picker tasks for GlitchTip, Pyroscope, Tempo, Loki, Faro, mutation, fuzz, contract, GitHub Actions, SonarQube, vmalert, and Rust defects.
   - New queue: `default`.
   - Idempotency key: source plus external id plus canonical fingerprint.
   - Cancellation: safe at page boundaries.
   - Retry: retry temporary API failures, do not duplicate already-filed findings.
   - Required proof: duplicate prevention tests and quota-refresh tests.

3. Scheduled updates:
   - Owner module: operations, reusing `backend/apps/scheduled_updates/runner.py`.
   - Current task examples: `scheduled_updates.run_next_scheduled_job`.
   - New queue: `default`.
   - Idempotency key: scheduled job id plus planned run time.
   - Cancellation: cooperative through existing checkpoint behavior.
   - Retry: existing missed-run and alert rules remain authoritative.
   - Required proof: pending job selection, Redis lock behavior, WebSocket progress, and missed-run alert tests.

4. Content import and crawler jobs:
   - Owner module: content or sources, exposed through public API.
   - Current task examples: XenForo import, WordPress import, crawler refresh, crawler prune.
   - New queue: `pipeline` if long-running, otherwise `default`.
   - Idempotency key: source system plus object id plus import window.
   - Cancellation: finish the current page or current content item, then stop.
   - Retry: retry temporary network failures with backoff; do not retry permanent authentication failures without filing an issue.
   - Required proof: mocked external service tests and external-wait benchmark separation.

5. Pipeline scoring, suggestions, embeddings, and link health:
   - Owner module: pipeline or suggestions through public API.
   - Current task examples: link-health checks, suggestion generation, embedding audit, embedding bakeoff, provider health, monthly tuning.
   - New queue: `pipeline` or `embeddings`.
   - Idempotency key: content id or batch id plus signal version.
   - Cancellation: checkpoint at batch boundaries.
   - Retry: retry provider unavailability only when the provider contract says it is temporary; never silently switch providers.
   - Required proof: batch checkpoint tests, provider-error tests, memory profile, and a soak test.

6. Analytics and external telemetry sync:
   - Owner module: analytics through public API.
   - Current task examples: GA4 sync, Search Console sync, telemetry aggregation, spike checks.
   - New queue: `default` unless long-running data pulls need `pipeline`.
   - Idempotency key: provider plus account plus date window.
   - Cancellation: finish current API page, persist checkpoint, then stop.
   - Retry: retry rate-limit responses according to provider wait headers where available.
   - Required proof: rate-limit tests, checkpoint resume tests, and no duplicate row tests.

7. Notifications and operator-facing alerts:
   - Owner module: operations or governance.
   - Current task examples: notification checks, stale alert pruning, dashboard summary refresh.
   - New queue: `default`.
   - Idempotency key: notification type plus target id plus period.
   - Cancellation: safe before send; after send starts, record send attempt and prevent duplicate sends.
   - Retry: retry transport errors, not user-disabled channels.
   - Required proof: duplicate-send prevention and disabled-channel tests.

8. Retention, cleanup, and disk-pressure jobs:
   - Owner module: operations.
   - Current task examples: result cleanup, temporary artifact cleanup, stale issue close, disk pressure checks.
   - New queue: `default`.
   - Idempotency key: cleanup type plus cutoff timestamp.
   - Cancellation: safe between deletion batches.
   - Retry: retry database lock conflicts; stop when safety thresholds would be breached.
   - Required proof: before/after row counts, threshold abort tests, and no protected-volume deletion.

9. Benchmark, profiling, and health jobs:
   - Owner module: operations.
   - Current task examples: benchmark jobs, profile inspection, internal health checks, schedule recovery.
   - New queue: `default`, with benchmark jobs allowed to request `pipeline` only by spec.
   - Idempotency key: benchmark name plus commit sha plus fixture.
   - Cancellation: stop at fixture boundary and preserve partial evidence as failed, not passed.
   - Retry: do not auto-retry benchmark failures unless the failure is infrastructure-only and visible.
   - Required proof: profile availability, benchmark schema, and failed-benchmark AutoIssue filing.

10. Work queue and agent self-healing jobs:
   - Owner module: operations or governance.
   - Current task examples: work queue maintenance, repair attempts, self-healing status refresh if any Celery wrappers exist.
   - New queue: `default`.
   - Idempotency key: item kind plus item id plus repair attempt fingerprint.
   - Cancellation: safe before an external command starts; after a command starts, record the command result and stop before the next command.
   - Retry: retry only if the previous attempt is marked infrastructure-blocked, not if it failed a real test.
   - Required proof: claim/release tests, conflict tests, and no duplicate repair attempts.

The inventory command must flag each family as one of four states: `not-started`, `ready-for-migration`, `migrated`, or `blocked`. A blocked state must name the blocker in plain English, for example "Sonar token invalid", "Mint health unreachable", "missing regression test", or "profiling pipeline degraded".

### Slice 8.1 - SonarQube ingest and quality pickers

Given SonarQube has 996 open AutoIssues and the autoscan path has a known token failure,
When choosing the first task family,
Then migrate Sonar ingest and scanner-related scheduled jobs first after token repair.

Tasks:

- `auto_issues.ingest_sonarqube_findings`
- Any Sonar-related picker or quota refresh command.
- The schedule entry `sonarqube-findings-ingest`.

BDD:

Given SonarQube is reachable at `http://10.10.10.91:9000` and `SONAR_TOKEN` validates,
When the Go scheduler enqueues Sonar ingest,
Then the Go worker runs the Python bridge, imports Sonar findings, and records created, updated, merged, and skipped counts.

Given SonarQube returns HTTP 401,
When ingest runs,
Then the job fails visibly, files an AutoIssue with source `sonarqube` or agent as specified by the existing quota spec, and the Mint quality check remains red.

### Slice 8.2 - AutoIssue pickers and quota helpers

Given many session-start jobs are AutoIssue pickers,
When they move off Celery,
Then they should run through the Go scheduler with strong idempotency.

Tasks include pickers for GlitchTip, Pyroscope, Tempo, Loki, Faro, mutation, contract, GitHub Actions, SonarQube, vmalert, Rust defect, and agent drought helpers.

BDD:

Given a picker already filed a row for the same external id,
When the task runs again,
Then it updates or dedupes the existing AutoIssue and does not create duplicates.

### Slice 8.3 - Scheduled updates runner

Given `backend/apps/scheduled_updates/runner.py` already has the serial job runner logic,
When moving from Celery,
Then the Go runtime should call the existing runner entrypoint through the Python bridge and preserve its Redis lock, progress, WebSocket, and missed-job behavior.

BDD:

Given one scheduled update job is pending,
When the Go worker runs `scheduled_updates.run_next_scheduled_job`,
Then the existing runner picks one job, writes checkpoints, and broadcasts progress.

### Slice 8.4 - Notifications, cleanup, retention, and health checks

Given these jobs are low-risk and frequent,
When they migrate,
Then they should prove schedule accuracy and low memory before heavier pipeline jobs move.

BDD:

Given a cleanup job deletes rows,
When it runs through the new runtime,
Then it logs before and after counts and refuses deletion if the existing retention threshold would be breached.

### Slice 8.5 - Crawler and content sync jobs

Given external content sync jobs depend on outside services,
When migrating,
Then the benchmark must separate task-runner overhead from external network time.

BDD:

Given XenForo or WordPress is slow,
When the job runs,
Then the task runtime records the external wait separately and does not retry faster than the external service policy allows.

### Slice 8.6 - Pipeline, embeddings, and heavy jobs

Given heavy pipeline jobs are most likely to load large libraries,
When migrating them,
Then they must come after memory proof exists for light and medium jobs.

BDD:

Given a pipeline job historically ran in `celery-worker-pipeline`,
When the Go runtime owns it,
Then the process memory stays under the heavy-job budget, `/tmp` does not grow unbounded, and the job's trace reaches Mint observability endpoints.

## Phase 9 - SonarQube And SonarScanner Repair

Given the latest handoffs and scripts show Sonar autoscan failed with HTTP 401,
When repairing Sonar,
Then do token bootstrap and validation before claiming Sonar healthy.

Required changes:

1. Update `scripts/start-mint-quality-tools.ps1` if needed so it validates a generated or existing token by calling a token-authenticated SonarQube endpoint before writing `.env.mint-quality`.
2. Keep `SONAR_TOKEN` and Sonar admin credentials in local environment or a secret store only. Never track them in the repo.
3. Update `sonar-scanner` and `sonar-autoscan` Compose defaults so they target `http://10.10.10.91:9000` when running from Windows-facing paths, and `http://sonarqube:9000` only inside the Mint compose network when both scanner and SonarQube run on Mint.
4. Remove local `depends_on: sonarqube` assumptions from scanner paths that are meant to target Mint by URL.
5. Make autoscan fail clearly on 401 and preserve logs for `scripts/check-mint-quality-tools.ps1`.
6. Make autoscan write a success marker only after a real scanner `EXECUTION SUCCESS`.
7. Make `manage.py ingest_sonarqube_issues` validate `SONAR_TOKEN` before reading issues.
8. Make the scheduled Sonar ingest task use the new task runtime, not Celery.
9. Update `docs/specs/fr-sonarqube-autoissues.md` and `docs/specs/fr-mint-quality-tool-placement.md` with the Mint URL model.
10. Drain or classify the 996 open SonarQube AutoIssues as part of normal quota, not by hiding the source.

BDD acceptance:

Given `SONAR_TOKEN` is missing on Mint,
When `scripts/check-mint-quality-tools.ps1` runs,
Then it fails with a plain message naming the missing token.

Given `SONAR_TOKEN` is invalid,
When autoscan starts,
Then it logs HTTP 401, the check script fails, and an AutoIssue is filed or updated.

Given `SONAR_ADMIN_USER` and `SONAR_ADMIN_PASSWORD` are provided locally,
When `scripts/start-mint-quality-tools.ps1 -RefreshSonarToken` runs,
Then it generates a new token, copies only the Mint-only env file to Mint, prints `[MINT SONAR TOKEN: generated name=<name> token=hidden]`, and never prints the token value.

Given SonarQube returns `UP` and the token validates,
When autoscan runs,
Then scanner exits successfully, logs `EXECUTION SUCCESS`, and `check-mint-quality-tools.ps1` prints `[MINT SONAR AUTOSCAN: status=ok recent_success=yes]`.

Test-first requirements:

- PowerShell parser tests for token-generation failure messages.
- Compose parser tests for correct `SONAR_HOST_URL` by service and profile.
- Python unit tests for Sonar ingest token validation.
- Python tests for HTTP 401 handling.
- Integration smoke test that can run against Mint when explicitly enabled.

Mutation testing:

- Mutate 401 detection.
- Mutate token-missing branch.
- Mutate success-marker detection.
- Tests must catch all three.

## Phase 10 - Mint Quality And Observability Move, Excluding Go Sidecars

Given the user wants the other mentioned work moved to Mint but not Go sidecars,
When updating the split stack,
Then use a location-aware service catalog rather than a Windows-only list.

Replace `config/observability-services.json` shape with something like:

```json
{
  "services": [
    {"name": "loki", "owner_host": "mint", "health_url": "http://10.10.10.91:3100/ready"},
    {"name": "tempo", "owner_host": "mint", "health_url": "http://10.10.10.91:3200/ready"},
    {"name": "vmsingle", "owner_host": "mint", "health_url": "http://10.10.10.91:8428/health"},
    {"name": "vmagent", "owner_host": "mint", "health_url": "http://10.10.10.91:8429/health"},
    {"name": "vmalert", "owner_host": "mint", "health_url": "http://10.10.10.91:8880/health"},
    {"name": "alloy", "owner_host": "mint", "health_url": "http://10.10.10.91:12345/-/healthy"},
    {"name": "otel-collector", "owner_host": "mint", "health_url": "http://10.10.10.91:13133/"},
    {"name": "pyroscope", "owner_host": "mint", "health_url": "http://10.10.10.91:4040/ready"},
    {"name": "grafana", "owner_host": "mint", "health_url": "http://10.10.10.91:3000/api/health"},
    {"name": "postgres-exporter", "owner_host": "mint", "health_url": null},
    {"name": "sonarqube", "owner_host": "mint", "health_url": "http://10.10.10.91:9000/api/system/status"},
    {"name": "sonar-autoscan", "owner_host": "mint", "health_command": "docker logs since start must contain success or pending without 401"}
  ],
  "excluded_from_mint_move": [
    "services/sidecars and other existing Go sidecars"
  ]
}
```

The exact schema can differ, but it must describe location, health method, owner, and recovery command.

BDD acceptance:

Given a service is marked `owner_host=mint`,
When `check_observability_health` runs on Windows,
Then it checks Mint via HTTP or `docker --context mint`, not local `docker compose ps`.

Given a Mint-owned service is down,
When the health command runs,
Then it files a visible AutoIssue with recovery command `scripts/start-mint-quality-tools.ps1` or a more specific Mint start script.

Given a Windows-owned service is down,
When the health command runs,
Then it keeps using local Docker health.

Given an existing Go sidecar is listed in Docker Compose,
When the Mint move tests run,
Then they assert it remains out of the Mint quality move unless a future spec explicitly changes that.

Given observability exporters point to Mint endpoints,
When the backend emits logs, metrics, traces, and profiles,
Then Loki, VictoriaMetrics, Tempo, and Pyroscope on Mint receive queryable data.

Test-first requirements:

- Unit tests for service-catalog parsing.
- Unit tests for local Docker health probe.
- Unit tests for remote HTTP health probe.
- Unit tests for remote Docker context probe.
- Regression test that Mint-owned services are not treated as absent just because local Docker does not list them.
- Regression test that existing Go sidecars are not included in the Mint service list.
- Live smoke test behind an explicit flag for Mint health.

Mutation testing:

- Mutate owner-host dispatch.
- Mutate health success predicate.
- Mutate excluded-service filtering.
- Tests must catch these mutants.

## Phase 11 - Observability For The New Task Runtime

Given Celery currently has Pyroscope names like `xf-linker-celery-default`, `xf-linker-celery-pipeline`, and `xf-linker-celery-beat`,
When the new runtime starts,
Then it needs first-class observability names and no stale Celery-only checks.

New profile names:

- `xf-linker-taskrunner-scheduler`
- `xf-linker-taskrunner-default`
- `xf-linker-taskrunner-pipeline`
- `xf-linker-taskrunner-janitor`
- `xf-linker-taskruntime-python-bridge`

Required signals:

- Task enqueue count.
- Task claim count.
- Task success count.
- Task failure count.
- Task retry count.
- Dead-letter count.
- Queue depth per queue.
- Oldest pending age per queue.
- Schedule jitter.
- Job runtime.
- Runner overhead.
- Memory by process.
- Redis stream length.
- Pending entries by consumer.
- Cancellation count.
- Duplicate idempotency prevention count.

BDD acceptance:

Given a task completes,
When observability is queried,
Then metrics, trace, log line, and profile sample can be correlated by `task_id` and `trace_id`.

Given a task fails,
When the AutoIssue is filed,
Then it includes task id, task name, queue, attempt, trace id, and recovery hint.

Given the Go pprof endpoint is enabled,
When `go tool pprof` hits the profile endpoint,
Then it returns data within timeout and the runtime.SetCPUProfileRate proof shows 500 Hertz where configured.

Test-first requirements:

- Go tests for metrics labels.
- Python tests for trace context propagation.
- Integration test that failed task writes AutoIssue evidence.
- Timeout-aware pprof test.
- Regression test that no Celery profile names remain after final removal.

Mutation testing:

- Mutate metric names.
- Mutate task id propagation.
- Mutate pprof timeout.
- Tests must catch these mutants.

## Phase 12 - Global Pause And Maintenance Mode

Given this repo has pause and maintenance-mode plans,
When replacing Celery,
Then the new runtime must respect those controls better than Celery does today.

Required behavior:

- Global pause stops workers from claiming new non-exempt jobs.
- In-flight jobs finish if safe.
- Cancellation remains allowed during pause.
- Maintenance mode freezes write-heavy task families unless the task definition explicitly allows maintenance execution.
- Scheduler records deferred due jobs.
- Resume drains deferred jobs in priority order.
- The UI and diagnostics show how many jobs were deferred.

BDD acceptance:

Given global pause is active and 100 jobs are queued,
When workers poll,
Then no new job starts and the queue depth stays visible.

Given global pause is cleared,
When workers poll again,
Then jobs begin in priority order.

Given maintenance mode is active,
When `AppSetting` or provider configuration write jobs become due,
Then they defer and explain why.

Given a health-check job is marked maintenance-safe,
When maintenance mode is active,
Then it can still run.

Test-first requirements:

- Unit tests for pause rules.
- Unit tests for maintenance rules.
- Integration test for deferred-drain ordering.
- Regression test that scheduler does not drop due jobs during pause.

Mutation testing:

- Mutate pause flag read.
- Mutate maintenance-safe allowlist.
- Mutate deferred-drain ordering.
- Tests must catch these changes.

## Phase 13 - Final Celery Removal

Given every migrated task has no Celery route,
When final removal starts,
Then remove Celery only after a hard gate proves no active task uses it.

Final removal checklist:

1. Remove `celery` imports from application code.
2. Remove `@shared_task` decorators or replace with task runtime registration.
3. Remove `.delay`, `.apply_async`, `AsyncResult`, and `revoke` call sites.
4. Remove `config/celery.py`.
5. Remove `django_celery_beat` from installed apps.
6. Remove `django_celery_results` from installed apps.
7. Remove `CELERY_*` settings.
8. Remove Celery Compose services.
9. Remove Celery health checks.
10. Remove Celery profile names.
11. Remove Celery docs or update them to task-runtime docs.
12. Remove Celery retention jobs and replace with task-runtime retention.
13. Preserve historical Celery database tables until a separate archival spec says how to handle them.
14. Update `docs/PERFORMANCE.md`, `docs/MODULAR-MONOLITH.md`, `docs/modules/operations.md`, `docs/BUSINESS-LOGIC-CHECKLIST.md`, and runbooks that still say Celery.
15. Update `PLAIN-ENGLISH-RULE.md` glossary with the new task runtime terms.

BDD acceptance:

Given the final removal branch is ready,
When `rg -n "celery|Celery|django_celery|shared_task|apply_async|AsyncResult|revoke" backend docker-compose.yml docs frontend scripts` runs,
Then any remaining hits are either historical migration notes, tests asserting absence, or glossary entries explaining the old system.

Given Docker Compose is rendered,
When default Windows services are listed,
Then no `celery-worker-default`, `celery-worker-pipeline`, or `celery-beat` service exists.

Given the backend starts,
When Django imports installed apps,
Then it does not require `django_celery_beat` or `django_celery_results`.

Given the scheduler is running,
When a formerly-Celery schedule becomes due,
Then the Go scheduler enqueues it and the Go worker completes it.

Test-first requirements:

- Static absence test for Celery imports and calls.
- Compose absence test for Celery services.
- Django startup test without Celery apps.
- Schedule regression test for migrated entries.
- End-to-end task runtime smoke test.
- Documentation freshness test.

Mutation testing:

- Mutate static absence allowlist.
- Mutate registry task names.
- Mutate final-removal condition.
- Tests must catch these mutants.

## Phase 14 - Benchmark Iteration Loop

Given first implementations rarely hit 5x memory and 20x performance immediately,
When a benchmark fails,
Then iterate with measured changes, not guesses.

Iteration order:

1. Reduce Python process starts by batching bridge jobs where safe.
2. Reuse a small pool of backend bridge processes only if the spec proves memory remains under the target and no stale Django state leaks.
3. Batch Redis reads and acknowledgements.
4. Batch progress event writes.
5. Shorten task envelope payload.
6. Move simple pure-Python task wrappers into Go only when they contain no Django model logic.
7. Move CPU-heavy pure functions to C ABI libraries only with profiling proof.
8. Split queues only when contention is measured.
9. Add indexes to the task ledger only when query plans prove they are needed.
10. Remove redundant status writes.
11. Trim streams more aggressively after proving no pending work is lost.
12. Cap log volume and avoid per-job noisy logs.

Each iteration must record:

- Hypothesis.
- Before metric.
- Change made.
- After metric.
- Test command.
- Mutation command.
- Profiling command.
- Decision: keep, revert, or file follow-up.

BDD acceptance:

Given a benchmark misses the 20x target,
When an optimization is attempted,
Then the session records before and after metrics and keeps the change only if it improves the target without breaking correctness.

Given an optimization makes memory worse,
When tests still pass,
Then the optimization is still rejected unless it is required for correctness and a new memory plan is filed.

Given a benchmark passes once,
When the soak test repeats for 60 minutes,
Then the result must still pass before final removal.

## Phase 15 - Required Test Matrix

Every implementation slice must run the smallest focused tests first, then the wider checks when the slice is ready.

Minimum unit tests:

- Python task runtime API tests.
- Python task registry tests.
- Python bridge command tests.
- Python schedule migration tests.
- Python Sonar token and ingest tests.
- Python remote observability health tests.
- Go queue tests.
- Go worker tests.
- Go scheduler tests.
- Go janitor tests.
- Go pprof tests.

Minimum integration tests:

- Redis stream enqueue, claim, ack.
- Delayed job due movement.
- Worker crash and lease reclaim.
- Scheduler tick to job completion.
- Python bridge success and failure.
- Sonar ingest against mocked pages.
- Remote Mint health check with fake endpoints.
- Pause and resume.
- Maintenance defer and drain.

Minimum regression tests:

- No migrated task remains in Celery registry.
- No migrated call site uses `.delay` or `.apply_async`.
- No Celery Compose service remains after final removal.
- No Windows health false-red for Mint-owned services.
- No Sonar autoscan green state after HTTP 401.
- No unbounded Redis stream growth.
- No duplicate idempotency key execution.

Minimum mutation tests:

- Python mutation for task envelope validation.
- Python mutation for idempotency.
- Python mutation for Sonar 401 handling.
- Python mutation for remote health owner dispatch.
- Go mutation for claim and ack.
- Go mutation for retry and dead-letter.
- Go mutation for scheduler due calculation.
- Go mutation for cancellation.

Minimum profiling tests:

- Go pprof CPU profile endpoint returns within timeout.
- Go heap profile endpoint returns within timeout.
- Pyroscope or OpenTelemetry profile path receives samples.
- `inspect_profiles` result is attached to the handoff marker.

Minimum benchmark tests:

- Celery baseline saved.
- Go benchmark saved.
- Comparison command computes ratio.
- Comparison refuses mismatched fixtures.
- 60-minute soak logs memory and disk growth.

## Phase 16 - Files Likely To Change

This is a planning estimate, not permission to edit all files at once.

Likely new files:

- `docs/specs/fr-celery-replacement-task-runtime.md`
- `docs/specs/fr-task-runtime-benchmark-proof.md`
- `docs/specs/fr-task-runtime-schedule-catchup.md`
- `docs/specs/fr-task-runtime-migration-inventory.md`
- `docs/specs/fr-mint-quality-observability-placement.md`
- `docs/specs/fr-remote-observability-health.md`
- `docs/specs/fr-sonar-autoscan-token-bootstrap.md`
- `docs/specs/fr-celery-final-removal.md`
- `backend/apps/operations/task_runtime/...`
- `backend/config/management/commands/inventory_celery_tasks.py`
- `backend/config/management/commands/benchmark_task_runtime.py`
- `services/taskrunner/...`
- `config/task-runtime-schedules.yaml`
- `config/task-runtime-services.json`
- `config/observability-services.json` replacement or migration file.
- Tests under `backend/apps/operations/tests/`, `backend/config/tests/`, `services/taskrunner/...`, and existing app test folders.

Likely edited files:

- `docker-compose.yml`
- `backend/config/settings/base.py`
- `backend/config/settings/celery_schedules.py`
- `backend/config/catchup_registry.py`
- `backend/apps/auto_issues/tasks.py`
- `backend/apps/scheduled_updates/runner.py`
- `backend/apps/observability/management/commands/check_observability_health.py`
- `scripts/start-mint-quality-tools.ps1`
- `scripts/check-mint-quality-tools.ps1`
- `.githooks/check-observability-stack.py`
- `docs/PERFORMANCE.md`
- `docs/MODULAR-MONOLITH.md`
- `docs/modules/operations.md`
- `docs/BUSINESS-LOGIC-CHECKLIST.md`
- `docs/specs/fr-mint-quality-tool-placement.md`
- `docs/specs/fr-sonarqube-autoissues.md`
- `PLAIN-ENGLISH-RULE.md`
- `AGENT-HANDOFF.md`

Likely deleted in final phase only:

- `backend/config/celery.py`
- Celery Compose service blocks.
- Celery-only instrumentation code.
- Celery-only tests after replacement tests exist.

Do not delete historical data tables in the final Celery removal. Archive or drop them only under a later source-backed data-retention spec.

## Phase 17 - Slice Order For The Next Sessions

Slice C0 - Read and baseline:

Given the next agent begins,
When it starts this project,
Then it runs the ritual, reads this plan, creates the specs, inventories Celery, and records baseline memory and speed.

Slice C1 - Task envelope and API:

Given baseline exists,
When the Python task runtime API is added,
Then tests prove enqueue, idempotency, pause, maintenance, and schema validation.

Slice C2 - Go queue core:

Given the API writes envelopes,
When the Go Redis Streams worker core is added,
Then tests prove claim, ack, retry, cancellation, and dead-letter behavior.

Slice C3 - Go scheduler:

Given the queue core exists,
When the scheduler is added,
Then tests prove current Celery Beat entries can be represented and due jobs enqueue correctly.

Slice C4 - Sonar repair and first migrated task:

Given scanner token handling is broken,
When Sonar repair lands,
Then autoscan succeeds or fails visibly, and Sonar ingest runs through the new task runtime.

Slice C5 - Remote observability health:

Given moved Mint services are currently false-red on Windows,
When service catalog health lands,
Then Mint-owned services are checked by Mint URL or context, and existing Go sidecars are excluded.

Slice C6 - AutoIssue picker migration:

Given Sonar and observability are visible,
When pickers migrate,
Then session-start sources can be refreshed without Celery.

Slice C7 - Scheduled updates migration:

Given the serial runner already exists,
When it migrates,
Then existing progress, lock, and missed-job behavior stay intact.

Slice C8 - Cleanup, notifications, and health jobs:

Given lower-risk tasks remain,
When they migrate,
Then frequent jobs prove schedule stability.

Slice C9 - Crawler and content sync:

Given external services dominate runtime,
When sync jobs migrate,
Then overhead is measured separately from network wait.

Slice C10 - Pipeline and embeddings:

Given heavy jobs are risky,
When they migrate,
Then memory, profile, and soak tests pass before old routes are removed.

Slice C11 - Final Celery removal:

Given every task family is migrated,
When final removal runs,
Then all Celery imports, settings, services, instrumentation, and docs are removed or updated, with historical data preserved.

Slice C12 - Benchmark closure:

Given Celery is removed,
When the final benchmark suite runs,
Then memory is at least 5x lower, runner overhead is at least 20x faster, mutation tests pass, profiling proof is attached, and the handoff explains any external-wait exceptions.

## Known Risks And How To Handle Them

Risk: Python bridge startup cost hides Go gains.

Response: Measure it. If bridge startup dominates, introduce a capped bridge-process pool with strict Django connection cleanup and memory proof. Do not keep a pool if memory target fails.

Risk: Redis Streams data grows without bound.

Response: Add trim policy and tests in the first queue slice. No stream can exist without a retention rule.

Risk: a migrated task runs twice because old Celery route still exists.

Response: Static tests must fail when a migrated task remains in Celery registry or call sites. Remove old route in the same slice.

Risk: schedule catch-up floods the queue after downtime.

Response: Port `catchup_registry.py` rules into explicit schedule state. Catch-up is per-task, capped, and visible.

Risk: Sonar token fix leaks credentials.

Response: Token value never appears in tracked files, command output, or handoff. Scripts print `token=hidden`.

Risk: Mint health is red because cable is unplugged.

Response: The health command fails clearly with host unreachable and recovery text. It must not silently mark Mint checks skipped.

Risk: existing Go sidecars get dragged into Mint move.

Response: Add regression test that the Mint move list excludes `services/sidecars` and any existing Go sidecar named by the current service catalog.

Risk: 20x is impossible for full job runtime.

Response: Split runner overhead from business logic time. The 20x target applies to runner overhead. If full runtime is externally dominated, attach evidence and keep optimizing the part the replacement owns.

Risk: mutation tests are too slow.

Response: Run focused mutation tests for touched task-runtime code in the slice. Full mutation can run as a later wider gate, but final Celery removal cannot skip mutation.

Risk: the dirty worktree contains unrelated changes.

Response: Do not revert them. Read touched files carefully. Stage and commit only when explicitly requested and only after the quota and quality gates pass.

## Definition Of Done

The Celery replacement is done only when all of these are true:

- No production source imports Celery.
- No production source uses `@shared_task`, `.delay`, `.apply_async`, `AsyncResult`, or Celery revoke.
- No Docker Compose Celery service remains.
- No `django_celery_beat` or `django_celery_results` app is required at startup.
- Every former schedule is represented in the new scheduler registry.
- Every former queue task is represented in the new task registry or deliberately deleted with a spec-backed reason.
- Sonar autoscan has a valid token path, real success marker, and visible failure on HTTP 401.
- SonarQube open findings are imported through the new runtime.
- Mint-owned quality and observability services are checked remotely and no longer create false Windows absent issues.
- Existing Go sidecars are not moved as part of this plan.
- Unit tests pass.
- Regression tests pass.
- Mutation tests pass for touched Python and Go task-runtime code.
- Profiling proof is current.
- Benchmarks prove at least 5x less memory and at least 20x faster runner overhead.
- A 60-minute soak test shows no unbounded memory, disk, Redis, or Postgres growth.
- Docs, specs, glossary, runbooks, and handoff are updated in plain English.
- No marker is filed without the real command output or engineering evidence behind it.

## Copy-Paste Prompt For The Next Session

Use this prompt when starting the fresh session:

```
We are replacing Celery completely. First run the full repo session-start ritual. Then read docs/plans/celery-replacement-mint-sonar-next-session-plan.md. Focus only on the Celery replacement and the required supporting fixes: Sonar scan/token repair, Mint quality and observability move except existing Go sidecars, remote health checks, benchmarks, mutation tests, unit tests, regression tests, and profiling proof. Do not commit unless I ask. Do not delete protected volumes. Do not leave a converted task with both Celery and the new runtime. Start with specs, inventory, baseline, and tests.
```

Decision point: if the next session has time for only one implementation slice, do C0 and C4 first: inventory/baseline plus Sonar token and ingest migration. That gives the biggest immediate value because it removes a known failing quality gate and creates the measurement harness needed for the rest of the Celery replacement.
