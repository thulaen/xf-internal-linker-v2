# Pick #25 — Passage-level retrieval segmentation (Callan 1994)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 25 |
| **Canonical name** | Callan fixed-window passage segmentation |
| **Settings prefix** | `passages` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | `a4771e8` (PR-E, 2026-04-22) |
| **Helper module** | [backend/apps/sources/passages.py](../../backend/apps/sources/passages.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `PassageSegmentationTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_passages.py` (pending G6) |

## 2 · Motivation

Long documents are topically heterogeneous — a blog post might start
with a tutorial and end with news. Scoring the whole document
against a query dilutes the query-relevant passage's signal. Callan
1994 shows that **passage-level retrieval** — computing similarity
against the best-matching passage instead of the whole-doc average —
substantially improves precision with minimal infrastructure change.
The simplest variant (fixed-size token windows with overlap) is "
surprisingly effective" per Callan §5.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Callan, J. P. (1994). "Passage-level evidence in document retrieval." *Proceedings of the 17th ACM SIGIR Conference*, pp. 302-310. |
| **Open-access link** | <https://dl.acm.org/doi/10.1145/188490.188589> |
| **Relevant section(s)** | §4 — passage types (fixed window vs topical vs structural); §5 — empirical results showing fixed windows are competitive with smarter methods. |
| **What we faithfully reproduce** | Fixed-window tokenisation with overlap. |
| **What we deliberately diverge on** | We offer BOTH `segment_by_tokens` (pure token windows) and `segment_from_sentences` (sentence-aligned windows via pick #15) so callers pick the granularity their downstream needs. Callan only describes fixed windows. |

## 4 · Input contract

- **`segment_by_tokens(text: str, *, window_tokens: int = 150,
  overlap_tokens: int = 30) -> list[Passage]`**
- **`segment_from_sentences(sentences: Iterable[str], *,
  window_tokens: int = 150, overlap_tokens: int = 30) -> list[Passage]`**
- `window_tokens > 0`, `0 ≤ overlap_tokens < window_tokens`.
- Empty text → `[]`.

## 5 · Output contract

- `Passage(index: int, text: str, token_start: int, token_end: int,
  token_count: int)` frozen dataclass.
- **Invariants.**
  - Passages are non-empty and in order.
  - Consecutive passages overlap by exactly `overlap_tokens` tokens.
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `passages.enabled` | bool | `true` | Recommended preset policy | No | — | Off = whole-doc scoring |
| `passages.window_tokens` | int | `150` | Callan 1994 §5 — 150-300 tokens is the sweet spot; we pick lower end because BGE-M3 prefers shorter sequences | Yes | `int(64, 512)` | Bigger window = more context, worse precision |
| `passages.overlap_tokens` | int | `30` | Callan §5 — ~20 % overlap prevents query-phrase splits | Yes | `int(0, 128)` | Bigger overlap = more passages per doc, more compute |

## 7 · Pseudocode

See `apps/sources/passages.py`. Core loop:

```
function segment_by_tokens(text, window, overlap):
    tokens = text.split()
    stride = window - overlap
    passages = []
    pos = 0
    idx = 0
    while pos < len(tokens):
        end = min(pos + window, len(tokens))
        passages.append(Passage(
            index=idx,
            text=" ".join(tokens[pos:end]),
            token_start=pos,
            token_end=end,
            token_count=end - pos,
        ))
        if end == len(tokens): break
        pos += stride
        idx += 1
    return passages
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/embeddings.py` | Long article | Embed per-passage, store passage vectors alongside doc vector |
| `apps/pipeline/services/ranker.py` | Query + doc passages | Max-over-passages cosine instead of single doc-level cosine |

## 9 · Scheduled-updates job

None — inline with parse/embed.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~2× input string (passage text copies) | — |
| Disk | `N_passages × ~1 KB` per doc | — |
| CPU | ~10 µs per 1 KB text | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_short_text_single_passage` | Short-path |
| `test_long_text_overlapping_passages` | Windowing |
| `test_passage_token_offsets_consistent` | Determinism |
| `test_no_empty_passages` | Invariant |
| `test_sentences_aligned_when_segmenting_from_sentences` | Sentence variant |
| `test_window_less_than_overlap_rejected` | Input validation |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 × 5 KB articles | < 20 ms | > 200 ms |
| medium | 10 000 × 10 KB articles | < 3 s | > 30 s |
| large | 1 000 000 × 10 KB articles | < 10 min | > 2 h |

## 13 · Edge cases & failure modes

- **Single-sentence "doc"** — one passage with `token_count = N`.
- **All tokens identical** — windowing still produces deterministic
  offsets.
- **Very large overlap (> 50 %)** — allowed but produces many near-
  duplicate passages; `min_joint_count`-style filtering downstream
  handles that.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #15 PySBD | Sentence boundaries for `segment_from_sentences` |

| Downstream | Reason |
|---|---|
| BGE-M3 embedder | Passage-level embedding |
| #26 Entity salience | Sentence-coverage feature over passages |
| Ranker max-over-passages scoring | Primary consumer |

## 15 · Governance checklist

- [ ] `passages.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-E)
- [ ] Benchmark module
- [x] Test module (PR-E)
- [ ] TPE search space declared
- [ ] Embeddings pipeline wired (W2)
- [ ] Ranker max-over-passages wired (W3)
