# Recommended Preset — operator's plain-English reference

This document describes every setting in the project's default "Recommended" preset, what each one does in plain English, what value it starts at, and which spec backs the choice.

The preset lives in `backend/apps/suggestions/recommended_weights.py` (the `RECOMMENDED_PRESET_WEIGHTS` dict). Migrations seed each row into the `AppSetting` table via `get_or_create`, so any value you override through the settings page survives a Docker rebuild or migration re-run.

## How to read this document

Each section groups related keys (e.g. all the `pipeline.*` retrieval knobs together). Each row has:

| Key | Plain-English what it does | Default | Why this default |
|---|---|---|---|

## How the rule applies

Per [`DEFAULT-ON-RULE.md`](../DEFAULT-ON-RULE.md), every key here ships with a non-zero, sensible starting value — unless it specifically requires external data (Google Analytics, Search Console, Matomo, autotuner training history) we don't have on a fresh install. Off-by-default keys carry a `# DEFAULT-ON-RULE: external-data-gated` comment in their seeding migration.

## Audit summary (2026-05-09)

Out of **196 keys** in the Recommended preset, only **2** ship with a "false" / "0" / "off" value:

| Key | Value | Why off-by-default |
|---|---|---|
| `trafilatura_extractor.favor_recall` | `"false"` | The Trafilatura content extractor has two modes: favour-precision (the default — strict, fewer false positives) and favour-recall (broader, more false positives). The strict mode is correct on a forum corpus where post-content has a known structure. Operator can flip this on if extraction is missing real content. |
| `trafilatura_extractor.include_comments` | `"false"` | Whether to include comment threads in the extracted body. The default is to strip them — they bias the embedding toward off-topic chatter. Flip on if the forum's "comments" are actually first-class content. |

Both are deliberate operator-choice defaults, not defects. The standing default-on rule covers all future additions.

## Where to find the actual values

The dict at the top of `backend/apps/suggestions/recommended_weights.py` is the source of truth. Every value has a comment block above it citing the FR-XXX spec or paper that justifies the number. To regenerate this file's per-key tables, run:

```
docker compose exec backend python manage.py shell -c "
from apps.suggestions.recommended_weights import RECOMMENDED_PRESET_WEIGHTS
for k, v in sorted(RECOMMENDED_PRESET_WEIGHTS.items()):
    print(f'{k}\t{v}')
"
```

## Related governance

- [`DEFAULT-ON-RULE.md`](../DEFAULT-ON-RULE.md) — every new feature ships ON with a sensible starting value.
- [`CITATION-RULE.md`](../CITATION-RULE.md) — every default value needs ≥1 specific citation (DOI / patent / RFC / stable URL).
- [`PLAIN-ENGLISH-RULE.md`](../PLAIN-ENGLISH-RULE.md) — every settings UI element has a `peHelper` plain-English hover.
