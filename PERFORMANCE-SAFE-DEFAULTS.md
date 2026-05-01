# PERFORMANCE-SAFE-DEFAULTS.md — Forbidden Patterns For New AI Work

**Status:** PARAMOUNT. Every AI agent (Claude / Codex / Antigravity / Gemini / future) reads this before adding any new function or modifying an existing one.

## The Rule

New AI work must NOT add unbounded loops, unbounded table growth, duplicate artefacts, or Python-only hot paths without justification. C++ is preferred for hot paths; bounded retention is mandatory for new tables; complexity must be declared.

If you violate any of the patterns below, the pre-commit hook blocks the commit. To override per-instance, add `# noqa: perf-safe-defaults # justification: <one-line reason>`.

## Forbidden Patterns

### Unbounded Loops

❌ `while True:` with no break-condition or timeout.
✅ `for _ in range(MAX_ITERATIONS):` or `while condition and time.monotonic() - start < timeout:`.

❌ `for x in queryset:` over a `.objects.all()` that may be 100K+ rows.
✅ `for x in queryset.iterator(chunk_size=500):` — bounded memory.

❌ Recursive function with no depth limit.
✅ Recursion with explicit `max_depth=N` parameter, default 10.

### Unbounded Table Growth

❌ A new `models.Model` keyed by event/timestamp with no TTL or `nightly_data_retention` integration.
✅ Model declared in `apps/core/services/self_test_smoke.py:ARTIFACT_RULES` with `retention_field` set; OR a `RunPython` in the migration that registers it with the prune task.

❌ A "snapshot" pattern that creates a new row every time a value changes (linear growth in operator activity).
✅ `Superseded*` archive table with 7-day TTL, OR overwrite-in-place with one prior copy archived.

❌ `bulk_create` without `update_conflicts=True` on a per-content artefact (creates duplicates on re-run).
✅ `bulk_create(..., update_conflicts=True, unique_fields=[...])` (Django 5.2+).

### Duplicate Artefacts

❌ Two separate models storing the same content fingerprint (e.g. `ContentItem.embedding` + `ContentItem.embedding_v2`).
✅ Single `embedding` column + `embedding_model_version` to distinguish.

❌ Re-computing an aggregate on every request when the input rarely changes.
✅ Materialised view + Celery beat refresh (Phase 2.18 pattern).

❌ Two implementations of the same algorithm in different files (e.g. one in `services/` and one in `tasks.py`).
✅ Single implementation, imported wherever needed.

### Python-Only Hot Paths

❌ A function called per-candidate inside `score_destination_matches` written in Python only.
✅ C++ extension with Python fallback. See [`CPP-FIRST.md`](CPP-FIRST.md).

❌ A new sort/heap/similarity loop over more than 100 items without a C++ kernel.
✅ Use existing C++ extensions (`scoring`, `simsearch`, `passagesim`) or add a new one per CPP-RULES.

### Magic Numbers In Services

❌ Bare numeric literal in a service function (`if score > 0.85:`).
✅ Module-level constant with citation comment (`_FUZZY_MATCH_THRESHOLD = 85  # Joachims 2007 §3`).

### Silent Exceptions In Hot Paths

❌ `except Exception: pass` or `except Exception: logger.warning(...)` in a service function consumed by the ranker / pipeline / embedder.
✅ Wrap with `apps.audit.error_ingest.ingest_error()` so the error is visible on `/error-log` (deduped via fingerprint).

### Hardcoded Paths

❌ `/app/` or `C:\` literals in code outside `config/`.
✅ `pathlib.Path(__file__).parent` or `settings.MEDIA_ROOT` etc.

### TODOs Without Owners

❌ `# TODO: fix this later` with no link to a spec or issue.
✅ `# TODO(RPT-042): replace once OPQ codebook trainer ships` — links to the Report Registry entry.

## Mandatory Pre-Merge Checklist

Every new function or modified hot-path declares:

1. **Time complexity** — `O(1)`, `O(log N)`, `O(N)`, `O(N²)`. Anything ≥ `O(N²)` requires written justification.
2. **Space complexity** — peak memory in MB at the largest expected input.
3. **C++ alternative considered** — if Python, why not C++? (One-line answer.)
4. **Storage budget** — if new persistent storage, what's the per-row cost in bytes and the projected row count at 1 year?
5. **Failure mode** — what happens when the inputs are empty / null / way larger than expected?

The pre-commit hook will be extended (Phase 4.0a) to scan for the forbidden patterns + flag any new function lacking the checklist.

## Required Citations For Hot-Path Python

Any hot-path function written in Python (instead of C++) must cite **why** in a comment immediately above:

```python
# Hot path: called per-candidate. Python is acceptable here because
# the underlying RapidFuzz library is already C-extension-backed; a
# new pure-C++ kernel would not be measurably faster than the existing
# rapidfuzz._fuzz wrapper.
def _score_fuzzy_match(...): ...
```

If you can't write that comment, the function must be a C++ extension instead.

## Performance Regression Tests

Every PR runs the existing benchmark suite (`scripts/bench-cpp.ps1` + `scripts/bench-py.ps1`) and compares against `master`. A regression of more than 10 % on any benchmarked function blocks the merge unless an explicit waiver is in the commit message.

## Why This Rule Exists

The user is a vibe coder operating on an i5-12450H + RTX 3050 + 16 GB RAM + 59 GB free disk. Every Python loop that should be C++, every magic number that turns into a footgun, every unbounded table that fills the disk in three months — these all eventually become operator emergencies. The rule shifts the cost from "operator finds it broken" to "AI agent fixes it before commit".
