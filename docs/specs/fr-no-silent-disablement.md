# FR — No Silent Disablement

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]
[SPEC CITED: feature=no-silent-disablement kind=standard id=https://www.rfc-editor.org/rfc/rfc2119 verified_at=2026-05-26]
[SPEC CITED: feature=no-silent-disablement kind=technical_doc id=https://docs.docker.com/reference/cli/docker/compose/ verified_at=2026-05-26]
[SPEC CITED: feature=no-silent-disablement kind=technical_doc id=https://opentelemetry.io/docs/specs/semconv/resource/service/ verified_at=2026-05-26]

## Source Notes

- RFC 2119 defines `MUST` and `MUST NOT` as mandatory requirement words.
- Docker Compose profiles are explicit opt-in groups; a service moved behind a profile is not part of the default stack unless the profile is selected.
- OpenTelemetry service identity conventions treat service names and attributes as the visible way to identify running services in telemetry.

## Behavior

Given an agent disables, stops, removes, moves, profile-gates, credential-blanks, or route-changes any service, hook, picker, scheduled task, data path, telemetry path, quality gate, credential, or agent-control feature, When the change is reported as done, Then the disabled or moved state must be visible through a source-backed spec or runbook, a focused test or health check, and the handoff.

Given a dependency cannot run, When the agent cannot restore it in scope, Then the agent must fail clearly, explain the risk, and file or update an AutoIssue or PaperTrail entry when the failure creates follow-up work.

Given a service is intentionally optional, When it is moved behind a Docker Compose profile or similar opt-in mechanism, Then the operator-facing command to start or verify it must be documented and tested.

## Forbidden Outcomes

- A service disappears from the default stack with no profile, start command, or health check.
- A credential is blanked so an integration silently does nothing.
- A startup error is swallowed and reported as success.
- A telemetry, error, profile, or issue-filing path is disabled without a visible follow-up.
- A temporary disablement is left without a test-backed paper trail.

## Verification

- `.githooks/test_check_agent_rules_sync.py::test_no_silent_disablement_rule_is_shared` proves the shared agent files all carry the rule.
- Feature-specific tests, such as the GlitchTip Compose integrity tests, remain responsible for concrete service placement and credential checks.
