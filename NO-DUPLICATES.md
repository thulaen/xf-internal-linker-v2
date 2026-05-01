# NO-DUPLICATES.md — Project Anti-Duplication Rule

**Status:** PARAMOUNT. Every AI agent (Claude, Codex, Gemini, Antigravity, every future agent) reads this file before adding any new persistent storage.

## The Rule

No persistent storage may pile up duplicate artefacts. Every per-content artefact table follows:

> `(content_hash, signal_version)` skip-if-unchanged + supersede + retention.

If you add a new Django model that stores anything keyed by content (vector, sketch, code, summary, score, fingerprint), it MUST satisfy the four pieces below, or the pre-commit hook will block your commit.

## The Four Pieces

1. **Content-identity column.** A SHA-256 (or other stable hash) of the exact input that produced the row. Common names already in the codebase: `content_hash`, `embedding_text_hash`, `text_hash`, `content_fingerprint`. The column is `db_index=True` so the skip-filter query is fast.
2. **Signal-version column.** A short string identifying the model / preprocessing / algorithm version that produced the row. Common names: `embedding_model_version`, `signal_version`, `pq_code_version`, `opq_codebook_version`. Lets a model-swap trigger re-computation without dropping the table.
3. **Skip-if-unchanged guard.** The writer must `.exclude(...)` rows where both `content_hash` and `signal_version` already match the about-to-be-written values. The pattern lives at [`backend/apps/pipeline/services/embeddings.py:_compute_embed_text_hash`](backend/apps/pipeline/services/embeddings.py) and the exclude filter inside `generate_content_item_embeddings` shows the canonical shape.
4. **Supersede + retention.** When the writer DOES overwrite a row, the prior version moves to a `Superseded*` archive table OR is overwritten in place with a single archived copy. The `nightly_data_retention` Celery task (in [`backend/apps/pipeline/tasks.py`](backend/apps/pipeline/tasks.py)) prunes archives after a TTL — typically 7 days for embeddings, 90 days for crawler visits, longer for audit trails.

## Tables That Already Satisfy The Rule (reference list — extend, don't reinvent)

| Table | Identity | Version | Supersede mirror | Retention |
|---|---|---|---|---|
| `ContentItem.embedding` | `embedding_text_hash` | `embedding_model_version` | `SupersededEmbedding` | 7 days |
| `PassageEmbedding` | `embedding_text_hash` | `embedding_model_version`, `opq_codebook_version` | overwrite-in-place | bounded by parent FK |
| `CrawledPageMeta` | `(normalized_url, content_hash)` upsert | implicit (one row per content version) | n/a (data is the latest version) | tied to `CrawlerVisit` retention |
| `CrawlerVisit` | `(url, content_hash, timestamp)` | n/a | n/a | 90 days |
| `Sentence.embedding` | `Post.content_hash` cascade | `sentence_model_version` | overwrite-in-place | tied to parent |
| `OPQCodebook` | `corpus_signature` | `version` | older rows kept inactive for rollback | manual GC |
| `EmbeddingCostLedger` | `(job_id, provider)` upsert | n/a | accumulator | tied to job retention |

## Process Gates

1. **Pre-commit hook** at [`.githooks/check-no-duplicates-invariant.py`](.githooks/check-no-duplicates-invariant.py) scans new Django migrations for any model with FK to `ContentItem` (or another per-content parent) and confirms the four pieces are present. Failure blocks the commit with a one-paragraph fix template.
2. **CI auditor** at [`scripts/verify_dedup_invariant.py`](scripts/verify_dedup_invariant.py) walks all artefact tables monthly (or on every PR) and confirms each still satisfies the invariant. Catches regressions where a later migration drops the hash column.
3. **Boot-time self-audit** runs as part of [`apps/core/services/self_test_smoke.py`](backend/apps/core/services/self_test_smoke.py). If a new artefact table is added without the invariant, the operator sees a `/error-log` warning on the next backend boot.
4. **Gate B addition** in [`docs/RANKING-GATES.md`](docs/RANKING-GATES.md) §B6 — every new ranking signal report must declare three lines: `Content-hash key:`, `Signal-version field:`, `Retention days:`. Missing any of those three is a policy violation equivalent to skipping any other gate checkbox.

## Why This Rule Exists

The user is a vibe coder operating on an i5-12450H + RTX 3050 + 16 GB RAM + 59 GB free disk. Each new artefact table that re-runs on every pipeline tick burns one of those finite resources. Without the rule, a corpus that grows linearly produces table growth that's quadratic in time × signal-versions. The rule keeps growth at `O(unique content × current signal versions)` which scales with the corpus, not with how often you run the pipeline.

## Forbidden Patterns

- ❌ A new artefact table whose writer always inserts (no upsert, no skip filter).
- ❌ A `RunPython` migration that nulls a column without queueing the re-computation.
- ❌ A "snapshot" pattern that creates a new row every time a value changes (use `Superseded*` + 7-day TTL instead).
- ❌ Storing the same vector twice because it came from two sources (dedupe via `ContentItem.duplicate_of`).
- ❌ A periodic recalculation that ignores the existing `signal_version` and re-writes every row.

## When To Update This File

Whenever a new artefact table ships, add it to the table above with its four pieces. Whenever the retention TTL on an existing table changes, update the column. The pre-commit hook reads this file as the source of truth for "is the new table covered" — if the file isn't kept current, the hook produces false positives.
