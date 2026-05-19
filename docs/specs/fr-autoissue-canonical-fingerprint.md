# FR — AutoIssue canonical_fingerprint contract

[SPEC FRESHNESS: reviewed_at=2026-05-18 next_review=2026-06-18]
[SPEC CITED: feature=fr-autoissue-canonical-fingerprint kind=technical_doc id=docker-storage-volumes verified_at=2026-05-18]
[SPEC CITED: feature=fr-autoissue-canonical-fingerprint kind=academic_paper id=10.1109/SEQUEN.1997.666900 verified_at=2026-05-18]

## Problem

The `canonical_fingerprint` helper at `backend/apps/auto_issues/services/fingerprinting.py` produces a SHA1-truncated-to-16 hash of an AutoIssue's title plus optional culprit. Two distinct usage modes share the same function:

1. **Source-agnostic dedup** — GlitchTip events, internal `ingest_error` rows, Pyroscope hotspots all hash their title-plus-culprit so the same root cause across different sources lands on one AutoIssue row. Path information is intentionally normalised to `<path>` placeholder because two ImportErrors from different file paths represent the same logical bug.

2. **Path-aware lesson dedup** — `log_tdd_lesson` and `log_code_review_lessons` need DISTINCT rows per (file, title) pair so an agent logging a TDD cycle for one file does not silently overwrite a TDD cycle for another file. The 2026-05-18 AutoIssue #260 incident proved that the source-agnostic helper collapsed unrelated TDD lessons into one row.

## Fix

Add an optional `file=` keyword to `canonical_fingerprint`. When supplied, the helper switches to the path-title contract via a new `_path_title_fingerprint(file, title)` helper that:

1. Normalises slash direction with `file.replace("\\", "/")` so Windows and POSIX paths collapse to one fingerprint per logical path.
2. Strips leading and trailing slashes plus lowercases the whole path so case variation across operating systems does not produce distinct fingerprints.
3. Inserts an explicit `"::"` separator between path and title so a long path cannot accidentally collide with a short path plus a long title.
4. Hashes the combined string with SHA1 and returns the 16-character hex prefix.

The source-agnostic default (no `file=` kwarg) is unchanged for non-lesson callers.

## Acceptance criteria

```
Given two distinct (file, title) pairs
When canonical_fingerprint(file=p1, title=t1) and canonical_fingerprint(file=p2, title=t2) both execute
Then the two return values differ
And two distinct AutoIssue rows are created when log_tdd_lesson is called for each pair

Given the same (file, title) pair is supplied twice
When canonical_fingerprint runs both times
Then both calls return the same fingerprint
And the dedup branch in log_tdd_lesson bumps occurrence_count on the existing row

Given a Windows-style path and the POSIX-equivalent path with the same title
When canonical_fingerprint runs against each
Then both calls return the same fingerprint because directory boundaries are preserved but slash direction is normalised
```

## Sources

- Docker storage model — https://docs.docker.com/storage/storagedriver/
- Broder 1997 — "On the resemblance and containment of documents" (doi:10.1109/SEQUEN.1997.666900) — foundational paper on shingle-based document fingerprinting and the value of preserving structural boundaries during hashing for high-precision dedup.

## Regression test

`backend/apps/auto_issues/tests/test_canonical_fingerprint_path_distinct.py` carries four tests covering distinct-paths-distinct-fingerprints, same-path-different-titles, deterministic stability, and slash-direction collapsing.
