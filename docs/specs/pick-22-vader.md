# Pick #22 — VADER sentiment analyser

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 22 |
| **Canonical name** | VADER (Valence Aware Dictionary and sEntiment Reasoner) |
| **Settings prefix** | `vader` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | **DEFERRED** — needs `vaderSentiment` pip dep |
| **Helper module** | `backend/apps/parse/sentiment/vader.py` (plan path) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

A per-post sentiment score (positive / negative / neutral /
compound) lets the ranker penalise cross-suggesting a cheerful intro
post alongside a critical bug-report thread. It also surfaces in the
dashboard — "75 % of suggestions this week were positive-toned."
VADER uses a 7 500-word valence lexicon + 5 rules (punctuation,
capitalisation, degree modifiers, negation, contrastive conjunction);
Hutto & Gilbert 2014 show it matches human annotators on social-
media text at ~80 % F1.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Hutto, C. J. & Gilbert, E. (2014). "VADER: A parsimonious rule-based model for sentiment analysis of social media text." *ICWSM*. |
| **Open-access link** | <http://comp.social.gatech.edu/papers/icwsm14.vader.hutto.pdf> |
| **Relevant section(s)** | §3 lexicon construction; §4 rule list; §5 benchmark across tweets, movie reviews, editorials. |
| **What we faithfully reproduce** | `vaderSentiment.SentimentIntensityAnalyzer().polarity_scores(text)`. |
| **What we deliberately diverge on** | Nothing. |

## 4 · Input contract

- **`analyse(text: str) -> SentimentScore`**. Empty text → all zeros.

## 5 · Output contract

- `SentimentScore(neg: float, neu: float, pos: float, compound: float)`
  — neg+neu+pos = 1, compound in [-1, 1].

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `vader.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no sentiment score |
| `vader.positive_threshold_compound` | float | `0.05` | Hutto-Gilbert §3 default cutoff | Yes | `uniform(0.0, 0.3)` | Compound ≥ threshold → label `positive` |
| `vader.negative_threshold_compound` | float | `-0.05` | Hutto-Gilbert §3 default cutoff | Yes | `uniform(-0.3, 0.0)` | Compound ≤ threshold → label `negative` |

## 7 · Pseudocode

```
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
analyzer = SentimentIntensityAnalyzer()

function analyse(text):
    if not text.strip():
        return SentimentScore(neg=0, neu=0, pos=0, compound=0)
    s = analyzer.polarity_scores(text)
    return SentimentScore(**s)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | Clean body | Stores `compound` on `ContentItem`; UI shows a traffic-light icon |
| `apps/pipeline/services/ranker.py` | Source/target sentiment | Optional penalty for cross-tone suggestions |

## 9 · Scheduled-updates job

None — inline.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | 30 KB lexicon | library |
| Disk | 30 KB lexicon | pip install |
| CPU | < 100 µs per 1 KB text | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_positive_text_gets_positive_compound` | Direction |
| `test_negative_text_gets_negative_compound` | Direction |
| `test_neutral_returns_near_zero` | Threshold behaviour |
| `test_empty_returns_zeros` | Degenerate |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 posts | < 50 ms | > 500 ms |
| medium | 100 000 posts | < 10 s | > 2 min |
| large | 10 000 000 posts | < 30 min | > 6 h |

## 13 · Edge cases & failure modes

- **Sarcasm / irony** — VADER misses these; known limitation.
- **Non-English text** — lexicon is English-only; route via pick #14.
- **Very long text (novels)** — VADER's valence averaging dilutes signal; per-paragraph scoring is the workaround.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC | Normalised input |
| #14 FastText LangID | Skip non-English |

| Downstream | Reason |
|---|---|
| Ranker tone-pairing signal | Uses compound as a feature |

## 15 · Governance checklist

- [ ] Approve `vaderSentiment` pip dep
- [ ] `vader.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module written
- [ ] Benchmark module written
- [ ] Test module written
- [ ] TPE search space declared
- [ ] Pipeline wired (W2)
