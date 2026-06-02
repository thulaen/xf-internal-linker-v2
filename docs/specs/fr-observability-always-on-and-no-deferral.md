# FR — Observability-Always-On + No-Deferral discipline

[SPEC FRESHNESS: reviewed_at=2026-05-23 next_review=2026-06-23]

[SPEC CITED: feature=observability-always-on-and-no-deferral kind=technical_doc id=beyer-sre-book-2016 verified_at=2026-05-23]
[SPEC CITED: feature=observability-always-on-and-no-deferral kind=technical_doc id=opentelemetry-spec-1.42 verified_at=2026-05-23]
[SPEC CITED: feature=observability-always-on-and-no-deferral kind=technical_doc id=github-actions-2025 verified_at=2026-05-23]
[SPEC CITED: feature=observability-always-on-and-no-deferral kind=technical_doc id=docker-compose-spec verified_at=2026-05-23]

## Summary

This project has two ABSOLUTE rules added in 2026-05-22 that govern every
agent (Claude / Codex / Gemini / Antigravity / every future agent):

1. **Observability + quality stack must always be running.** Stopping a
   container in the observability or quality tier as a "workaround" to
   silence a hook, dodge an importer, suppress a finding, or otherwise
   avoid an honest check is FORBIDDEN.
2. **No-Deferral.** Every requirement that surfaces during a session
   must be completed in that session. Forbidden-phrase markers such as
   `deferred`, `skipped`, `will do later`, `workaround`, and bare
   `TODO`/`FIXME`/`XXX`/`HACK` tokens are HARD-BLOCKED at commit time
   unless they reference a paper-trail or AutoIssue row.

Both rules are enforced by new pre-commit hooks
(`.githooks/check-observability-stack.py` and
`.githooks/check-no-deferral.py`) that fire FIRST in
`scripts/precommit-docker.sh` so a missing observability container or
a forbidden-phrase marker fails before any other check runs.

## Why

The user observed two patterns in earlier sessions that this rule pair
ends:

* **Workaround-via-stop.** Agents had stopped the `sonarqube` and
  `sonar-autoscan` containers to make `manage.py ingest_sonarqube_issues`
  hit `SonarQubeUnavailable` and silently skip the re-open path. That is
  a deferral disguised as a workaround. It also leaves the entire
  observability stack — Pyroscope, GlitchTip, Loki, Tempo, Grafana,
  VictoriaMetrics — at risk of being stopped for similar reasons.
* **Silent deferral.** Agents had written `we'll handle that in a
  follow-up session` or `out-of-scope this session` without filing a
  paper-trail entry. Deferred work that is not in the database is lost
  work. This rule pair ends that pattern by treating the forbidden
  phrases as commit-blocking markers.

## Behavior

### Observability stack (Rule 1)

`scripts/precommit-docker.sh` invokes
`.githooks/check-observability-stack.py` as the first hard gate after
`tool-readiness`. The hook queries `docker compose ps --format json` for
each of the 14 long-running containers in the observability + quality
tier:

```
sonarqube, sonar-autoscan, glitchtip, glitchtip-worker,
pyroscope, postgres-exporter, otel-collector, vmsingle, vmagent,
vmalert, loki, alloy, tempo, grafana
```

`glitchtip-init` is intentionally excluded from the hook's list because
it is a one-shot init job whose normal lifecycle is to run once at boot
and exit; treating an exited init job as a failure would block every
commit after the first start. The rule still applies to the rest of
the stack.

**Host split (2026-05-29).** `sonarqube`, `sonar-autoscan`, and `pyroscope`
were moved off Windows onto the Mint helper (the `mint-quality` Compose
profile; see `config/docker-stack-health.json` and
`docs/specs/fr-mint-quality-tool-placement.md`). They remain always-on, but
on Mint. The hook no longer expects them in the local `docker compose ps`
output; instead `config/observability-services.json` lists them under
`remote_services`, and `.githooks/check-observability-stack.py` verifies each
over the network via its `health_url` (SonarQube `/api/system/status`,
Pyroscope `/ready`). The deep verifier is `scripts/check-mint-quality-tools.ps1`.
Restart these three with `scripts/start-mint-quality-tools.ps1`, never a local
`docker compose up`. The 11 remaining containers stay on Windows and are still
checked locally.

The hook PASSES when every container is in `State=running` AND
`Health` is either `starting`, `healthy`, or empty (no healthcheck
declared). The hook FAILS when any container reports `State` other
than `running`, OR `Health` of `unhealthy`, `restarting`, `exited`, or
when the container is absent. The failure message names the down
container and gives the exact `docker compose up -d <name>` command to
restart it.

### No-deferral (Rule 2)

`.githooks/check-no-deferral.py` scans the staged
`AGENT-HANDOFF.md` diff plus the staged source-code diffs (including
comments) for the following forbidden phrases (case-insensitive,
word-boundary match):

```
deferred, deferring, defer to, skip, skipping, skipped for, leave for,
leaving for, out of scope, out-of-scope, next session, follow-up session,
future work, will be done later, will handle in, postponed, postponing,
not in this session, silent retry on hook block, silent code-review skip,
silent deferral, no-op the importer
```

The four code-comment tokens `TODO`, `FIXME`, `XXX`, `HACK` are
FORBIDDEN as bare tokens but ACCEPTED when immediately followed (same
line, same comment) by `(paper-trail #<N>)` or `(AutoIssue #<N>)`
referencing a real DB row. The hook validates the row exists via
`manage.py shell -c` query.

When any forbidden phrase or bare `TODO`-family token is found, the
hook HARD-BLOCKS the commit with a Rule-F three-part FAIL message
listing the file, line, and matched phrase plus the accepted
escape-valve syntax for code comments.

## Source backing

* Beyer, B., Jones, C., Petoff, J., Murphy, N.R. (2016). *Site
  Reliability Engineering: How Google Runs Production Systems*. O'Reilly.
  ISBN 978-1491929124. Chapters 6-7 establish that observability stacks
  are not optional during incident response or normal operation; this
  spec adapts that principle to local dev: the stack stays up so the
  next incident is observable.
* OpenTelemetry Specification 1.42 (2025).
  https://opentelemetry.io/docs/specs/otel/ — section "Resource and
  Instrumentation Scope" requires that telemetry pipelines be reachable
  from running services for the trace + metric flow to be useful. The
  observability-always-on rule keeps that pipeline available.
* GitHub Actions documentation (2025).
  https://docs.github.com/en/actions/learn-github-actions — section
  "Workflow events" defines push and pull_request triggers; the CI side
  of the soft-gate / hard-gate split (Phase J.6) relies on these
  triggers and the no-deferral rule keeps the deferral discipline
  consistent across local + CI.
* Docker Compose specification.
  https://docs.docker.com/compose/compose-file/ — defines `services` /
  `healthcheck` / `restart` semantics that the observability stack
  relies on. The hook calls `docker compose ps --format json` per the
  Compose Engine's documented JSON output.

## Behavior tests

The pre-commit hooks are TDD-armed:
`.githooks/test_check_observability_stack.py` and
`.githooks/test_check_no_deferral.py` exercise happy-path + the named
failure cases (container down, container restarting, forbidden phrase
in handoff, bare TODO without link, TODO with valid paper-trail
reference, TODO with invalid paper-trail reference, multi-violation
listing). The tests run under `pytest -p randomly` and use
`unittest.mock.patch` to stub the docker + Django subprocess calls so
no live service is required.

## Rollout

This commit is the first to install the rules and the enforcing hooks
together. Every subsequent commit therefore runs under the new
discipline. A missing observability container or a forbidden-phrase
marker becomes a hard block from this commit forward.

## Forbidden phrases

`deferred`, `silent deferral`, `silently moving on`, `no-op the
importer`, `workaround`, `bypass`, `skip the hook`, and the same list
documented in `check-no-deferral.py` are not used in this spec's
narrative because the spec itself must remain compliant with the rule
it documents.
