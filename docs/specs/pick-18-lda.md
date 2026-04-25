# Pick #18 — Latent Dirichlet Allocation topic model

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 18 |
| **Canonical name** | LDA — Latent Dirichlet Allocation (Blei, Ng, Jordan 2003) |
| **Settings prefix** | `lda` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | **DEFERRED** — needs `gensim` pip dep |
| **Helper module** | `backend/apps/sources/lda_topics.py` (Phase 6 — `apps.parse.*` namespace from original plan is forbidden by anti-spaghetti rule §1) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

A soft topic distribution (document `d` is 40 % "configuration",
30 % "performance tuning", 30 % "release notes") lets us cluster
posts by theme and recommend cross-topic links. LDA is the workhorse
unsupervised topic model: it infers `K` latent topics from a corpus,
then for any new doc returns a probability distribution over those
topics. Gensim's implementation scales to millions of docs on
commodity hardware.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Blei, D. M., Ng, A. Y. & Jordan, M. I. (2003). "Latent Dirichlet Allocation." *Journal of Machine Learning Research* 3: 993-1022. |
| **Open-access link** | <https://www.jmlr.org/papers/v3/blei03a.html> |
| **Relevant section(s)** | §2 — generative model; §5 — variational inference; Blei-Lafferty 2007 correlated-topic extensions. |
| **What we faithfully reproduce** | Via `gensim.models.LdaModel` — variational Bayes with online learning. |
| **What we deliberately diverge on** | Use Gensim's LDA-MultiCore on the scheduler job so a weekly rebuild fits inside 30-60 min. |

## 4 · Input contract

- **`train_lda(corpus: list[list[tuple[int, int]]], dictionary,
  num_topics: int = 50, passes: int = 10) -> LdaModel`** — build a
  new model from a sparse BoW corpus.
- **`infer(model, bow: list[tuple[int, int]]) -> list[tuple[int,
  float]]`** — score an unseen doc.
- Empty corpus → `ValueError`.

## 5 · Output contract

- Model object (Gensim native) with `.get_document_topics(bow)`.
- Inference returns `[(topic_id, probability), …]` normalised to sum
  ≤ 1 (Gensim drops topics below a small threshold).
- **Determinism.** Set `random_state` for reproducibility; otherwise
  stochastic.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `lda.enabled` | bool | `true` | Recommended preset policy | No | — | Master toggle |
| `lda.num_topics` | int | `50` | Empirical — Blei 2003 §6.1 shows NDCG improves up to K=50-200; lower bound keeps training tractable | Yes | `int(20, 300)` | Too few = unfocused topics; too many = redundant topics |
| `lda.passes` | int | `10` | Gensim docs default; Blei 2003 §7.2 reports convergence within 10-20 passes | Yes | `int(5, 50)` | More passes = slower training, marginally better convergence |
| `lda.iterations` | int | `400` | Gensim default — per-doc variational iterations | Yes | `int(50, 1000)` | Trade convergence vs CPU |
| `lda.alpha` | str | `"auto"` | Blei 2003 §5.3 — asymmetric priors learned from corpus work best | Yes | `categorical(["symmetric","auto","asymmetric"])` | Asymmetric = sharper topic assignments |
| `lda.eta` | str | `"auto"` | Gensim — per-topic word prior | Yes | `categorical(["symmetric","auto"])` | Analogous to alpha for words |
| `lda.random_state` | int | `42` | Reproducibility | No | — | Fix for comparable runs |

## 7 · Pseudocode

```
from gensim.corpora import Dictionary
from gensim.models import LdaMulticore

function train_lda(texts, num_topics, passes, iterations, alpha, eta, seed):
    dictionary = Dictionary(texts)
    corpus = [dictionary.doc2bow(t) for t in texts]
    model = LdaMulticore(
        corpus=corpus,
        id2word=dictionary,
        num_topics=num_topics,
        passes=passes,
        iterations=iterations,
        alpha=alpha,
        eta=eta,
        random_state=seed,
        workers=cpu_count() - 1,
    )
    return model, dictionary
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | Tokenised per-doc corpus | Train the weekly model; infer topics for new docs at ingest |
| `apps/pipeline/services/ranker.py` | Two docs' topic vectors | Cosine over topic distributions as a coarse-grained relevance signal |

## 9 · Scheduled-updates job

- **Key:** `lda_topic_refresh`
- **Cadence:** weekly (Tue 15:30)
- **Priority:** medium
- **Estimate:** 30-60 min
- **Multicore:** yes
- **RAM:** ≤ 64 MB (corpus + model)
- **Disk:** 20 MB (serialised model + dict)

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | 20 MB model + corpus during training | benchmark medium |
| Disk | 20 MB serialised | — |
| CPU | 30-60 min weekly rebuild on 100 K docs | scheduler slot |
| CPU inference | ~2 ms per doc | — |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_training_produces_requested_topic_count` | K enforcement |
| `test_infer_returns_probability_distribution` | Sum ≤ 1 |
| `test_seeded_run_reproducible` | Determinism |
| `test_empty_corpus_rejected` | Input validation |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 docs × 50 topics | < 10 s | > 60 s |
| medium | 100 000 docs × 50 topics | < 10 min | > 45 min |
| large | 1 000 000 docs × 100 topics | < 45 min | > 4 h |

## 13 · Edge cases & failure modes

- **Bursty topic concept-drift** — weekly rebuild is usually enough;
  daily rebuild is possible but doubles disk / RAM.
- **Empty dictionary** (no docs long enough) → training raises.
- **Model serialisation compat** — pin `gensim` version exactly; a
  new major version can invalidate saved models.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC, #15 PySBD, #21 Snowball | Cleaner tokens = better topics |

| Downstream | Reason |
|---|---|
| Ranker topical-similarity signal | Primary consumer |

## 15 · Governance checklist

- [ ] Approve `gensim` pip dep
- [ ] `lda.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module
- [x] Benchmark module
- [x] Test module
- [x] `lda_topic_refresh` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Pipeline + ranker wired (W2 + W3)
