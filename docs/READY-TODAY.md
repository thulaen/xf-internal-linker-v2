# Ready Today — what's running right now (no jargon edition)

> Last updated: 2026-04-25 (Wire phase + Polish.A/B shipped). If you're a new operator coming back to this, this is the first thing to read.

## TL;DR

**The system is working. You don't have to do anything.** Every "optional" feature from the 52-pick research plan is installed, switched on by default, and either already producing results or scheduled to start producing results within 7 days.

Open `http://localhost/` → log in → that's your dashboard. The ranker is doing its job. The Diagnostics page tells you how well.

---

## What's switched on right now (and what "switched on" means)

**Important distinction** — "switched on" means two different things in this system, and the docs need to be precise:

- **Live in the ranker right now**: every Suggestion you see in the review queue had this signal computed and added to `score_final`. You'd notice immediately if it stopped.
- **Helper installed + ready, but not yet a live scoring contributor**: the pip package + model file are present, the helper module returns real values when called, the AppSetting toggle exists, scheduled training jobs fire on cadence — but the ranker's `score_destination_matches` doesn't yet call it. To consume the helper, a future commit would add a `score_<pick>` column on `Suggestion` and call the helper from the ranker.

Both states are "ready to go", but only the first state changes today's review-queue results.

### Live in the ranker right now (every Suggestion benefits today)

| Pick | Where you see it |
|---|---|
| Semantic similarity (BGE-M3) | `score_semantic` |
| Keyword match | `score_keyword` |
| PageRank (FR-006) | `score_march_2026_pagerank` |
| HITS authority + hub | Inside `score_node_affinity` (W3c GraphSignalRanker) |
| TrustRank, PPR (#30, #36) | Inside `score_node_affinity` (same ranker) |
| Anchor diversity | `score_anchor_diversity` |
| Phrase relevance, field-aware relevance, learned anchor, rare term, GA4/GSC, click distance, freshness, FR-099..105 (DARB/KMIG/TAPB/KCIB/BERP/HGTE/RSQVA) | Each has a dedicated `score_*` column |
| RRF fusion (#31) | Used in candidate fusion when Group C retrievers are enabled |
| Conformal Prediction #50 + ACI #52 | `confidence_lower_bound` / `confidence_upper_bound` |
| Uncertainty Sampling #49 | Review queue ordering |
| Platt Calibration #32 | `calibrated_probability` |
| Elo #35 | `score_elo_rating` |
| Auto-Seeder #51 + TrustRank seed selection | Daily scheduled refresh; consumed by HITS/PPR/TrustRank |
| Position-bias IPS #33 + Cascade Click #34 | Persisted to AppSetting + read by feedback_relevance consumer; populates `score_*` indirectly |
| Group C Stage-1 retrievers (Lexical #C.2 + QueryExpansion #C.3) | Off by default; flip via Settings → "Stage-1 Candidate Retrievers" |

### The 10 Phase 6 helpers — installed, toggleable, NOT yet live in the ranker

These were the focus of this week's "Wire phase". Each has: pip dep installed, paper-backed defaults seeded in `AppSetting`, a toggle in Settings → "Optional Pick Toggles", lazy-import wrapper, tests, benchmarks, and (where applicable) a weekly scheduled training job that produces real model files.

**They are NOT yet wired into the per-Suggestion scoring loop.** The ranker (`apps/pipeline/services/ranker.py::score_destination_matches`) doesn't call them yet. Wiring each one requires a follow-up PR that:
1. Adds a `score_<pick>` column to the `Suggestion` model + migration
2. Calls the helper inside the ranker's per-candidate loop
3. Adds the column to `recommended_weights.py` blend

| Pick | Status today | What lights up after wiring |
|---|---|---|
| **VADER #22** (Hutto-Gilbert 2014) | Helper available; toggle on; not consumed | Sentiment-aware ranking; sentiment shown on suggestion-detail dialog |
| **PySBD #15** (Sadvilkar-Neumann 2020) | Helper available; toggle on; not consumed | More-accurate sentence splits in the parse pipeline |
| **YAKE! #17** (Campos 2020) | Helper available; toggle on; not consumed | Keyword diagnostics on suggestion-detail dialog |
| **Trafilatura #7** (Barbaresi 2021) | Helper available; toggle on; not consumed | Used at crawl time when external HTML import lands |
| **FastText LangID #14** (Joulin 2016) | Helper + 131 MB model available; toggle on; not consumed | Non-English content suppression in candidate pool |
| **LDA #18** (Blei-Ng-Jordan 2003) | Helper available; weekly W1 trains a real model from corpus titles; not yet consumed | Topical-similarity feature in ranker |
| **KenLM #23** (Heafield 2011) | Helper + lmplz binary available; weekly W1 trains real model; not yet consumed | Anchor fluency scoring |
| **Node2Vec #37** (Grover-Leskovec 2016) | Helper available; weekly W1 trains real embeddings; not yet consumed | Graph-structure feature on ranker |
| **BPR #38** (Rendle 2009) | Helper available; weekly W1 fits on approve/reject; not yet consumed | Personalised ranking score |
| **Factorization Machines #39** (Rendle 2010) | Hand-rolled NumPy helper available; weekly W1 fits on Suggestion features; not yet consumed | Pairwise feature-interaction score |

**Why the gap exists:** the original 52-pick plan separated "ship the helper" (Phases 6.1–6.5) from "wire it into the ranker" (the per-pick PRs that would add `Suggestion.score_<pick>` columns). The Wire phase finished the first half; the second half is per-pick follow-up.

---

## What you have to do (TL;DR: nothing today)

### Nothing

The Wire phase already:
- Installed all 10 pip dependencies in the production Docker image.
- Downloaded the 131 MB FastText language-ID model (`/opt/models/lid.176.bin`).
- Built the KenLM training tool (`lmplz`) from source so weekly retraining works.
- Seeded ~40 paper-backed default values via database migration `0043_seed_phase6_pick_defaults` + `0044_fasttext_path_to_opt`.
- Set every pick's `*.enabled` flag to `true` so nothing is dormant.

### Eventually (you can ignore these)

The system trains some models on a schedule. They'll auto-fire — you don't have to click anything:

- **Daily 13:00–23:00** (the operator-window scheduler):
  - PageRank, HITS, TrustRank, PPR refresh
  - Auto-seeder (TrustRank seed picker)
  - Near-duplicate clustering refresh
  - **NDCG@10 smoke test** — Polish.B's daily quality readout (see Diagnostics page)
- **Weekly**:
  - LDA topic model retrain
  - KenLM trigram retrain (uses `lmplz` binary)
  - Node2Vec random walks + embedding retrain
  - BPR refit on your approve/reject feedback
  - Factorization Machines refit
  - Position-bias IPS η refit
  - Cascade Click EM refit
- **Monthly**:
  - Product Quantization codebook refit (compresses embeddings)

If you want any of these to run **right now** instead of waiting for cadence: open the dashboard → "Scheduled Updates" tab → click "Run Now" on the job.

### If you want manual control

Open `http://localhost/settings`. Scroll to "Optional Pick Toggles" (right after the Group C Stage-1 Retrievers section). Each of the 10 Phase 6 picks has its own toggle with a tooltip citing the paper. Flip any **off** if you want to disable it. Hit "Save optional pick toggles". The next pipeline run honours your choice.

---

## How do I know if any of this actually works?

Three places to check:

1. **`http://localhost/diagnostics`** → scroll to "Retriever Quality (NDCG@10)". Polish.B's automated benchmark fires daily and shows you how well your ranker orders approved suggestions over rejected ones. Higher = better. Comes with a 95% confidence interval and a per-retriever-source breakdown. Cold start (first 50 reviewed Suggestions): says "Approve more, then this reads".

2. **`http://localhost/settings`** → see all the toggles, each with paper citations in tooltips. If something says "Enabled" it's contributing.

3. **`http://localhost/dashboard`** → "Scheduled Updates" tab → see when each W1 job last ran and whether it succeeded. If a model file got produced, the next pipeline pass uses it automatically.

---

## The "configured at code/install time" jargon, translated

When I said "everything that doesn't need real running data is done":

| Jargon | Plain English |
|---|---|
| pip dependencies installed | Python packages downloaded and ready |
| Docker image built | The container running the backend has all the tools |
| AppSetting defaults seeded | Every knob has a paper-backed starting value in the database |
| Scheduled jobs registered | The weekly/daily training jobs know they exist and when to run |
| Cold-start safe | When data is missing, the system politely returns "neutral" instead of crashing |
| Real-data ready | The first time data shows up, everything wires through automatically |

So "ready today" means: **as soon as you start running the pipeline (which happens automatically on a schedule), every feature kicks in. No operator setup needed.**

---

## What if something looks broken?

1. The Diagnostics page (`http://localhost/diagnostics`) lists every service's health. Red = broken.
2. The Scheduled Updates tab on the dashboard shows the last 20 runs of every job, with "missed" alerts deduped by day so you don't drown.
3. Every Suggestion row has a `score_*` for every signal — if a column is unexpectedly all-zero, that signal is silently failing. Check the Suggestion-detail dialog ("Why this score?") for diagnostics.
4. If you want to see exactly what's installed: `docker-compose exec backend pip list | grep -i "vader\|gensim\|kenlm\|implicit\|node2vec\|trafilatura\|yake\|pysbd\|fasttext"`. All ten should be there.

---

## TL;DR (one more time)

**Nothing for you to do today.** The system runs itself. Open the dashboard and start reviewing suggestions — that's the only operator-side action that matters. Every other feature is either active right now or training itself in the background.

If you want to disable anything: Settings → Optional Pick Toggles → flip → Save. That's it.
