# FR — Self-Healing Agent Rollback

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Detect proven backend or frontend breakage caused by the latest agent-authored commit and prepare a rollback decision that reverts only that latest agent commit. The system must never revert user-authored work or uncommitted dirty worktree changes.

## Sources Of Truth

- Git official documentation for revert semantics, `https://git-scm.com/docs/git-revert`.
- Django deployment checklist and health-check practices, `https://docs.djangoproject.com/en/stable/howto/deployment/checklist/`.
- Angular build and test documentation, `https://angular.dev/tools/cli/test`.
- SRE Workbook, "Alerting on SLOs", Google, `https://sre.google/workbook/alerting-on-slos/`.

## Safety Rules

1. Only the newest commit may be considered.
2. The commit must be attributed to an agent, not the user.
3. Backend or frontend health must be proven broken by a check result.
4. Dirty local work must block automatic revert.
5. Manual review mode exposes `POST /api/work-queue/self-healing/<id>/approve/`.

## Behavior

### Scenario: latest agent commit breaks backend

Given the latest agent commit breaks backend health,  
When self-healing verifies the failure,  
Then the decision says only that commit is eligible for revert.

### Scenario: user commit is latest

Given the latest commit is user-authored,  
When self-healing evaluates the repository,  
Then the decision is blocked and no revert command is suggested.

### Scenario: dirty worktree

Given the worktree has uncommitted changes,  
When self-healing evaluates a failing health check,  
Then the decision is manual review because automatic revert could destroy work.

## Output Shape

The GUI receives:

- latest commit hash;
- author classification;
- backend health;
- frontend health;
- decision status;
- plain-English reason;
- allowed action.


[SPEC CITED: feature=fr-self-healing-agent-rollback kind=technical_doc id=https://git-scm.com/docs/git-revert verified_at=2026-06-02]
