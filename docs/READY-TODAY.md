# Ready Today — what's running right now (no jargon edition)

> Last updated: 2026-04-25 (Wire + Polish + scheduler 11–23 + retention in window + Phase 6 dispatcher with **all six ranker-time picks wired** + parse-time picks (FastText LangID filter, PySBD splitter, YAKE keyword boost, Trafilatura HTML extractor) plumbed). If you're a new operator coming back to this, this is the first thing to read.

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
| **VADER #22 sentiment** (new) | Wired into `score_final` via `phase6_ranker_contribution`. Operator-tunable via `vader_sentiment.ranking_weight` AppSetting (default 0.0 → no effect; raise to 0.05–0.20 to start using). |

### The 10 Phase 6 helpers — installed, toggleable, NOT yet live in the ranker

These were the focus of this week's "Wire phase". Each has: pip dep installed, paper-backed defaults seeded in `AppSetting`, a toggle in Settings → "Optional Pick Toggles", lazy-import wrapper, tests, benchmarks, and (where applicable) a weekly scheduled training job that produces real model files.

**They are NOT yet wired into the per-Suggestion scoring loop.** The ranker (`apps/pipeline/services/ranker.py::score_destination_matches`) doesn't call them yet. Wiring each one requires a follow-up PR that:
1. Adds a `score_<pick>` column to the `Suggestion` model + migration
2. Calls the helper inside the ranker's per-candidate loop
3. Adds the column to `recommended_weights.py` blend

| Pick | Status today | What lights up after wiring |
|---|---|---|
| **VADER #22** (Hutto-Gilbert 2014) | **Wired in the ranker.** Recommended weight `0.05`. Per-candidate compound × 0.05 lands on `score_final`. | Sentiment-aware ranking on every Suggestion — already running. |
| **KenLM #23** (Heafield 2011) | **Wired in the ranker.** Recommended weight `0.05`. Per-host-sentence `tanh(per_token + 3)` × 0.05. Cold-start safe — fluency = 0.0 until the W1 weekly trainer writes the first ARPA file. | Fluent host sentences get a small lift; ungrammatical ones a small demote. |
| **LDA #18** (Blei-Ng-Jordan 2003) | **Wired in the ranker.** Recommended weight `0.10`. Cosine-of-topic-mixtures over host + destination texts. Cold-start safe — 0.0 until the W1 weekly LDA trainer fires. | Topical similarity gets fed into `score_final` once a model exists. |
| **Node2Vec #37** (Grover-Leskovec 2016) | **Wired in the ranker.** Recommended weight `0.05`. Cosine of per-node embeddings. Cold-start safe — 0.0 until W1 weekly Node2Vec trainer writes embeddings. | Graph-community signal complements PageRank/HITS/PPR/TrustRank. |
| **BPR #38** (Rendle 2009) | **Wired in the ranker.** Recommended weight `0.05`. `tanh(BPR-score / 2)`. Cold-start safe — 0.0 until W1 weekly BPR refit fires (≥ 5 reviewed Suggestions). | Personalised pairwise LTR signal. |
| **Factorization Machines #39** (Rendle 2010) | **Wired in the ranker.** Recommended weight `0.10`. `tanh(FM-prediction)`. Cold-start safe — 0.0 until W1 weekly FM refit fires. | Feature-interaction signal (Rendle 2010 §3 eq. 1-3). |
| **PySBD #15** (Sadvilkar-Neumann 2020) | **Wired into the sentence splitter.** Used as the default backend when its dep + toggle are both active; spaCy stays the parallel parse for downstream NER / POS. | More-accurate sentence boundaries on forum prose — every distillation + ranker pass benefits. |
| **YAKE! #17** (Campos 2020) | **Wired into the distiller.** Adds a small per-sentence boost (0.05 per matching keyword, capped at 0.4) when distilled sentences contain document-level YAKE keywords. | Distilled body skews toward sentences carrying the document's most salient terms. |
| **Trafilatura #7** (Barbaresi 2021) | **Wired into the crawler.** Replaces the BeautifulSoup-strip-and-`get_text()` step in `site_crawler._parse_html`. Falls through to BeautifulSoup when trafilatura is unavailable. | Crawled pages get clean main-content text instead of "everything between the boilerplate". |
| **FastText LangID #14** (Joulin 2016) | **Wired into the candidate pool.** `pipeline_data` drops content records whose title is detected as non-English (default `und` is kept — defensive). Off-toggle and missing-dep paths return the dict verbatim. | Non-English content stops slipping into the candidate pool. |

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

- **Daily 11:00–23:00** (the operator-window scheduler — widened from 13–23 → 11–23 on 2026-04-25 to give two extra hours of capacity):
  - PageRank, HITS, TrustRank, PPR refresh
  - Auto-seeder (TrustRank seed picker)
  - Near-duplicate clustering refresh
  - **NDCG@10 smoke test** — Polish.B's daily quality readout (see Diagnostics page)
  - GSC spike detection (moved from 08:00 → 11:00 — the laptop is asleep at 8 am)
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
