# AutoIssue And Paper-Trail Quota Hard Block

[SPEC FRESHNESS: reviewed_at=2026-06-06 next_review=2026-09-02]

## 1. Quota definition (non-substitutable)

This spec restores hard refusal at exactly two Git moments: commit and push.
"Hard refusal" means the command exits with a non-zero status so Git stops the
action.

The configured session quota is:

- Up to 77 resolved AutoIssues since the previous handoff timestamp.
- 10 resolved paper-trail entries since the previous handoff timestamp.

The 77 AutoIssue ceiling splits as:

- 30 resolved across the ten non-SonarQube source buckets, with at least 3 from
  each bucket: agent, glitchtip, pyroscope, tempo, faro, mutation, fuzz,
  contract, gh_ci, and vmalert.
- 10 resolved with `source="sonarqube"`.
- 10 resolved with `source="rust_defect"`.
- Up to 10 resolved with `source="pprof"`.
- Up to 10 resolved with `source="alloy"`.
- Up to 7 resolved with `source="loki"`.

The Python+Rust migration supersedes removed-runtime native observability work.
Sources tied only to retired runtime tooling are excluded from the live hard
quota before the database availability calculation runs. As of ADR 0007 and
`docs/PYTHON-RUST-MIGRATION-PLAN.md`, that retired hard-source set is:
`pprof`, `perfetto`, and `gwp_asan`. Rust and Python issues remain live.

Resolved means all of these are true:

- `status='resolved'`.
- `resolved_at` is later than the previous handoff timestamp.
- `lessons_learned` contains both `Trap:` and `Fix shape:` for AutoIssues.
- `resolution_lessons` contains both `Trap:` and `Fix shape:` for paper-trail
  entries.

The verifier calculates the live requirement for each source from the database:

```text
live_required_for_source =
  min(configured_source_quota, unresolved_rows_for_source + resolved_this_session_for_source)
```

This makes the quota drought-aware without hardcoded numbers. If a source has
zero unresolved rows and zero rows resolved this session, that source requires
zero for the commit. If a source has 15 available rows and its configured
quota is 30, resolving those 15 rows satisfies that source. If the source has
more rows than the configured quota, the configured quota remains the ceiling.

The SonarQube, rust_defect, alloy, and loki buckets are still
non-substitutable when work exists. Resolving cross-source AutoIssues does not
satisfy an available SonarQube, rust_defect, alloy, or loki shortfall.

The non-substitution rule comes from the existing SonarQube AutoIssue spec,
which says the session quota is 30 existing source fixes plus 10 SonarQube
fixes. The existing daily picker spec defines bounded AutoIssue picking. The
paper-trail spec defines the 10 resolved paper-trail entries per session.

## 2. Session boundary detection

The previous session starts at the most recent handoff header in
`AGENT-HANDOFF.md` matching:

```text
^# \d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+-\s+
```

The timestamp is parsed as `YYYY-MM-DD HH:MM`. If the file has no prior session
header, the verifier treats the repository as a fresh checkout and passes with a
plain message that includes `grandfather: no prior session`.

## 3. Commit check

A new hook named `.githooks/check-autoissue-quota.py` runs from
`scripts/precommit-docker.sh` after `.githooks/check-paper-trail-read.py`.

The hook runs both commands:

```bash
docker compose exec -T backend python manage.py ingest_sonarqube_issues
docker compose exec -T backend python manage.py verify_autoissue_quota --hard --since-handoff
docker compose exec -T backend python manage.py verify_paper_trail_quota --hard --since-handoff
```

The commit refuses if any command exits with a non-zero status.

## 4. Push check

`scripts/prepush-docker.sh` runs the same two commands before the slower language
checks:

```bash
docker compose exec -T backend python manage.py ingest_sonarqube_issues
docker compose exec -T backend python manage.py verify_autoissue_quota --hard --since-handoff
docker compose exec -T backend python manage.py verify_paper_trail_quota --hard --since-handoff
```

The push refuses if any command exits with a non-zero status. The refusal
text must match the commit check text for the same quota shortfall.

## 5. No bypass

No environment variable disables these checks. `XF_QUALITY_ENV=ci` does not
disable them. There is no quota-skip flag, no empty-commit exception, no override
file, and no substitution between the cross-source buckets and the SonarQube
count.

## 6. Drift handling

Docker down, the backend container not running, or the database being unreachable
must fail closed. The hook returns exit code 2 and writes:

```text
FAIL quota: cannot verify (Docker down). UNBLOCK: start Docker Desktop and re-run.
```

No local fallback may mark the check as passed.

## 7. Plain-English FAIL message

A quota failure must name the exact shortfall. The message includes:

- The previous handoff timestamp.
- The configured totals: up to 77 AutoIssues and 10 paper-trail entries.
- A per-bucket AutoIssue breakdown.
- A dedicated line for each short source showing observed resolved rows,
  live available requirement, and configured quota.
- For the zero-resolved, available-work case, a line like:
  `sonarqube: 0 of 4 available resolved (NON-SUBSTITUTABLE - must come from source=sonarqube)`.
- For a partial shortfall, a line like:
  `sonarqube: 5 of 10 resolved (5 short)`.
- A clear note that resolving more cross-source AutoIssues cannot make up for
  an available mandatory-bucket shortfall.
- The next open AutoIssue IDs or paper-trail entry IDs selected by the program
  from the database, so the operator does not manually choose rows.
- The SonarQube importer runs before the counts, so SonarQube picks come from
  the current scanner data instead of a manual handoff list.
- An unblock command for AutoIssues using `manage.py resolve_autoissue`.
- An unblock command for paper-trail entries using `manage.py resolve_paper_trail`.

## Behavior

Given the database has at least the configured quota available for every source
and those configured quotas are resolved after the previous handoff, when the
commit or push check runs, then both verification commands exit 0 and Git
continues.

Given a source has fewer available rows than its configured quota and every
available row from that source is resolved after the previous handoff, when the
commit or push check runs, then the source passes without inventing extra rows.

Given a source has zero available rows, when the commit or push check runs, then
that source requires zero resolved rows and does not block the commit.

Given a source is retired by the Python+Rust migration, when unresolved rows
from that source still exist, then those rows do not add to the hard quota.

Given SonarQube has available unresolved rows and 0 SonarQube AutoIssues are
resolved, when the commit or push check runs, then the check exits 2 and states
that the available SonarQube work cannot be substituted.

Given Docker cannot run the backend command, when the hook runs, then it exits 2
with the fail-closed Docker message.

## Sources

- [SPEC CITED: technical_doc] `docs/specs/fr-sonarqube-autoissues.md`, reviewed
  2026-05-20. Source for 30 existing source fixes plus 10 SonarQube fixes.
- [SPEC CITED: technical_doc] `docs/CPP-DAILY-ISSUE-PICKER-SPEC.md`, reviewed
  2026-05-18. Source for bounded AutoIssue picking and source-bucket discipline.
- [SPEC CITED: technical_doc] `docs/PAPER-TRAIL.md`. Source for the 10
  resolved paper-trail entries per session.
- [SPEC CITED: technical_doc] Git project, "githooks", latest page read
  2026-05-20, https://git-scm.com/docs/githooks. Source for commit and push hook
  execution points.
- [SPEC CITED: technical_doc] Django Software Foundation, "Writing custom
  django-admin commands", page read 2026-05-20,
  https://docs.djangoproject.com/en/3.2/howto/custom-management-commands/.
  Source for management command arguments and command failure handling.
- [SPEC CITED: technical_doc] Docker, "docker compose exec", page read
  2026-05-20, https://docs.docker.com/compose/reference/exec/. Source for
  running verification commands inside the backend container with `-T`.
- [SPEC CITED: technical_doc] `docs/adr/0007-python-rust-two-language.md`,
  reviewed 2026-06-06. Source for C, C++, Go, Haskell, and removed native
  observability retirement.
- [SPEC CITED: technical_doc] `docs/PYTHON-RUST-MIGRATION-PLAN.md`, reviewed
  2026-06-06. Source for retiring native-observability AutoIssue feeders while
  keeping Rust and Python issues live.

[SPEC CITED: feature=autoissue-quota-hard-block kind=technical_doc id=https://git-scm.com/docs/githooks verified_at=2026-06-02]
