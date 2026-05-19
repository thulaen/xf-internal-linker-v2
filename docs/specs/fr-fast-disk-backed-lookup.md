# FR - Fast disk-backed resolved-issue lookup

[SPEC FRESHNESS: reviewed_at=2026-05-18 next_review=2026-06-18]
[SPEC CITED: feature=fr-fast-disk-backed-lookup kind=technical_doc id=python-json-3.14 verified_at=2026-05-18]
[SPEC CITED: feature=fr-fast-disk-backed-lookup kind=technical_doc id=python-pathlib-3.14 verified_at=2026-05-18]
[SPEC CITED: feature=fr-fast-disk-backed-lookup kind=technical_doc id=python-argparse-3.14 verified_at=2026-05-18]
[SPEC CITED: feature=fr-fast-disk-backed-lookup kind=technical_literature id=978-0321146533-Beck-2002 verified_at=2026-05-18]

## Problem

The per-file resolved-history rule needs one lookup for every touched file.
The Django command writes the right audit proof, but it pays Django startup
cost each time. Large commits can touch hundreds of files, so the lookup step
must support a direct disk path that avoids Django startup while preserving the
same audit-log schema.

## Contract

`scripts/lookup_disk_index.py` reads `audit/resolved_issues_index.jsonl`,
accepts one or more `--area` values, prints matching resolved lessons for each
exact file path, and appends one row per area to
`audit/resolved_issues_lookup_log.jsonl`.

Each audit row must contain:

- `file_path`
- `lookup_at`
- `task_id`
- `agent`
- `result_count`
- `result_ids`

The file path normalisation must match the existing Django helper: convert
backslashes to forward slashes, trim whitespace, and strip leading or trailing
slashes.

## Behaviour

Given an area that exists in the JSON-lines index.
When the helper runs for that area.
Then it prints the matching AutoIssue ids and writes an audit row with a
positive result count.

Given an area that has no prior lessons.
When the helper runs for that area.
Then it prints a zero-match line and still writes an audit row, because the
absence of prior lessons is proof that the lookup happened.

Given malformed JSON-lines input.
When the helper reads the index.
Then it skips malformed rows and continues with the valid rows.

Given several `--area` arguments.
When the helper runs once.
Then it appends one audit row per area in the same process.

## Performance target

The helper must complete a lookup against the current repository index in less
than 200 ms wall-clock time on the user's current machine. The design is one
linear pass over a JSON-lines file, followed by dictionary lookups for each
area. At 10x entries, this stays one file scan. At 100x entries, the next
feature lands as a generated offset index beside the JSON-lines file if a
measured run exceeds the target.

## Sources

- Python documentation 3.14 - `json`, source for JSON-lines decoding through
  `json.loads` and the documented `JSONDecodeError`.
  https://docs.python.org/3/library/json.html
- Python documentation 3.14 - `pathlib`, source for path handling through
  `Path`.
  https://docs.python.org/3/library/pathlib.html
- Python documentation 3.14 - `argparse`, source for repeated command-line
  options through `action="append"`.
  https://docs.python.org/3/library/argparse.html
- Beck 2002 - Test-Driven Development: By Example. ISBN 978-0321146533.

## Regression test

`scripts/test_lookup_disk_index.py` covers path normalisation, malformed rows,
exact matching, repeated areas, audit-log writing, task-id detection, CLI
output, missing-index behaviour, and the 200 ms local performance budget.
