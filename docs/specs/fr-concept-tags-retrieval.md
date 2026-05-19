# FR - Concept-tagged lesson retrieval

[SPEC FRESHNESS: reviewed_at=2026-05-18 next_review=2026-06-18]
[SPEC CITED: feature=fr-concept-tags-retrieval kind=academic_paper id=10.1145/1135777.1135862 verified_at=2026-05-18]

## Problem

Lessons are filed by repository path today. That means a trap found in one
folder is easy to miss when the same trap appears in another folder. For
example, a Python subprocess call that needs explicit UTF-8 handling on Windows
can first appear under `.githooks/`, then appear again under `scripts/` or
`backend/apps/`.

## Fix

Add a controlled-vocabulary `concept_tags` field to AutoIssue. Logging commands
can attach one or more approved tags to a lesson or test-case row. Retrieval
commands gain a `--tag` flag. When tags are supplied, retrieval uses the union
of tag matches and the existing path match. In plain terms, the command returns
lessons that match either the folder or the concept.

## Behaviour

Given a resolved lesson in `.githooks/` is tagged `python-subprocess`, When the
next agent runs lesson retrieval for `scripts/` with `--tag python-subprocess`,
Then the `.githooks/` lesson is included even though its file path is outside
`scripts/`.

Given a command is passed an unknown tag, When the command validates the input,
Then it stops with a plain-English error and points the user to
`manage.py list_concept_tags`.

## Source

Marlow, Naaman, Boyd, and Davis (2006) studied tagging as a retrieval aid across
contexts. The cited paper supports this feature's use of a controlled tag list
to improve lesson lookup without adding a new search system.

## Citations

- Marlow, C., Naaman, M., Boyd, D., and Davis, M. 2006. HT06, tagging paper,
  taxonomy, Flickr, academic article, to read. DOI 10.1145/1135777.1135862.
