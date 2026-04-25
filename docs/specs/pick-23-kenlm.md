# Pick #23 — KenLM trigram language model

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 23 |
| **Canonical name** | KenLM trigram language model (Heafield 2011) |
| **Settings prefix** | `kenlm` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | **DEFERRED** — needs `kenlm` pip dep + `lmplz` trainer binary |
| **Helper module** | `backend/apps/sources/kenlm_lm.py` (Phase 6 — `apps.parse.*` namespace from original plan is forbidden by anti-spaghetti rule §1) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

A trained trigram LM scores how "natural" a piece of text sounds:
`LM_prob("The quick brown fox")` is high; `LM_prob("Brown fox quick
the")` is low. The linker uses this as a fluency signal — noise,
auto-translated spam, and spun content all score poorly. KenLM is
the fastest open-source implementation (by far; Heafield 2011 shows
it 2-10× faster than SRILM / IRSTLM) and uses a compact trie so a
trigram model trained on 100M tokens fits in ~50 MB RAM.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Heafield, K. (2011). "KenLM: Faster and smaller language model queries." *Proceedings of the Sixth Workshop on Statistical Machine Translation (WMT)*, pp. 187-197. |
| **Open-access link** | <https://aclanthology.org/W11-2123/> |
| **Relevant section(s)** | §3 — trie data structure; §4 — Kneser-Ney smoothing; §5 — benchmark. |
| **What we faithfully reproduce** | `kenlm.Model.score(sentence)`. Trainer is the C++ `lmplz` binary shipped with KenLM. |
| **What we deliberately diverge on** | Nothing algorithmic. Adapter handles model-file path resolution and provides per-sentence scoring with length normalisation. |

## 4 · Input contract

- **`score(model: kenlm.Model, text: str) -> float`** — returns
  `log10(P(text))` under the LM, normalised by length.
- Empty text → `-math.inf` (no probability).

## 5 · Output contract

- `float` — log-prob per word. Higher (closer to zero) = more
  natural.
- **Invariants.**
  - `score("")` → `-inf`.
  - `score(well-formed English)` usually in `[-3, -1]`.
  - `score(word-salad)` usually `< -5`.
- **Determinism.** Deterministic per model.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `kenlm.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no fluency score |
| `kenlm.model_path` | str | `"var/models/corpus.trigram.arpa"` | Project convention | No | — | Model identity |
| `kenlm.order` | int | `3` | Heafield 2011 — trigrams are the sweet spot for fluency at low memory | No | — | Higher `n` = bigger model, slightly better fluency but 5× disk |
| `kenlm.length_normalise` | bool | `true` | Standard — compares short vs long texts fairly | No | — | Correctness |
| `kenlm.retrain_cadence_days` | int | `7` | Weekly scheduled retrain | Yes | `int(1, 30)` | More frequent = faster adaptation to new corpus vocabulary |

## 7 · Pseudocode

```
import kenlm
from functools import lru_cache

@lru_cache(maxsize=2)
def load_model(path):
    return kenlm.Model(path)

function score(model, text):
    if not text.strip():
        return float("-inf")
    log_prob = model.score(text.lower(), bos=True, eos=True)
    tokens = max(1, len(text.split()))
    return log_prob / tokens    # length-normalise
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | Cleaned body | Stores `fluency_score` on `ContentItem` |
| `apps/pipeline/services/ranker.py` | Candidate pair scores | Down-rank suggestions with very low fluency |
| `apps/pipeline/services/keyword_stuffing.py` (existing) | Complementary | KL divergence catches stuffing, KenLM catches nonsense |

## 9 · Scheduled-updates job

- **Key:** `kenlm_retrain`
- **Cadence:** weekly (Wed 15:30)
- **Priority:** medium
- **Estimate:** 15–30 min
- **Multicore:** yes
- **RAM:** ≤ 64 MB (training + model)
- **Disk:** ≤ 50 MB (ARPA model file)

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM (scoring) | ~50 MB (loaded model) | Heafield 2011 |
| RAM (training) | ~200 MB for 100M-token corpus | `lmplz` docs |
| Disk | 50 MB trigram model | — |
| CPU | ~50 µs per sentence | Heafield §5 |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_natural_english_higher_than_word_salad` | Direction |
| `test_empty_returns_minus_inf` | Degenerate |
| `test_length_normalised_score_comparable_across_lengths` | Normalisation |
| `test_unknown_words_dont_crash` | Robustness |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 sentences | < 100 ms | > 1 s |
| medium | 100 000 sentences | < 10 s | > 2 min |
| large | 10 000 000 sentences | < 30 min | > 6 h |

## 13 · Edge cases & failure modes

- **Model file missing** — `OSError` at load; scheduled retrain
  re-creates.
- **Vocabulary drift** — new corpus words score low; weekly retrain
  addresses.
- **Domain mismatch** — scoring cooking-blog text against a
  gaming-corpus LM produces misleading scores; we train per-corpus.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC, #15 PySBD | Tokenisation |

| Downstream | Reason |
|---|---|
| Ranker fluency signal | Primary consumer |

## 15 · Governance checklist

- [ ] Approve `kenlm` pip dep + `lmplz` binary
- [ ] `kenlm.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module written
- [x] Benchmark module written
- [x] Test module written
- [x] `kenlm_retrain` scheduled job registered (W1)
- [ ] TPE search space declared
- [x] Pipeline wired (W2)
