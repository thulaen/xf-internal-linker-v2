# GlitchTip Direct Findings

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Summary

GlitchTip is the local error tracker. It receives events through Sentry-style
SDKs and exposes issue/event APIs that agents can read before fixing captured
errors. When GlitchTip shows a repeated runtime error, the fix must target the
real app path that created the event, not only the imported AutoIssue summary.

## Source-Backed Notes

- GlitchTip documents Sentry SDK compatibility for sending error events.
- GlitchTip contributor docs reference issue event JSON from
  `/api/0/issues/<issue-id>/events/latest/` for compatibility testing.
- Sentry's issue API documents listing project issues, retrieving issues, and
  listing issue events; GlitchTip aims to keep the same API shape.
- Celery beat schedules run named tasks. A stale task name in the schedule can
  reach workers and fail before application code runs.
- Django documents that after a database error inside an atomic transaction,
  later queries in the same transaction raise `TransactionManagementError` until
  the rollback completes.

## Behavior

Given the XenForo base URL is blank or still the placeholder host, when the
health check runs, then the search check returns "not configured" and does not
make a network request.

Given Celery beat schedules the OPQ codebook training job, when the worker
receives the task, then the task name matches the registered
`pipeline.train_opq_codebook` task.

Given the weekly reviewer scorecard task runs, when it checks for an existing
scorecard or creates a new one, then it references the `ReviewerScorecard`
model explicitly and does not raise `NameError`.

Given a database operation fails inside a transaction, when follow-up handling
would otherwise query through the same broken transaction, then the app should
avoid compounding the original database error with a second query.

## Sources

- [SPEC CITED: technical_doc] GlitchTip, "SDK Documentation,"
  https://glitchtip.com/sdkdocs/
- [SPEC CITED: technical_doc] GlitchTip, "Contribute Documentation,"
  https://glitchtip.com/documentation/contribute/
- [SPEC CITED: technical_doc] Sentry, "Events and Issues API,"
  https://docs.sentry.io/api/events/
- [SPEC CITED: technical_doc] Celery, "Periodic Tasks,"
  https://docs.celeryq.dev/en/v5.2.5/userguide/periodic-tasks.html
- [SPEC CITED: technical_doc] Django, "Database transactions,"
  https://docs.djangoproject.com/en/4.1/topics/db/transactions/

[SPEC CITED: feature=fr-glitchtip-direct-findings kind=technical_doc id=https://glitchtip.com/sdkdocs/ verified_at=2026-06-02]
