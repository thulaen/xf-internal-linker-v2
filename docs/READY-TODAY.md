# Ready Today — what's running right now (no jargon edition)

> Last updated: 2026-04-25 (Wire phase + Polish.A/B shipped). If you're a new operator coming back to this, this is the first thing to read.

## TL;DR

**The system is working. You don't have to do anything.** Every "optional" feature from the 52-pick research plan is installed, switched on by default, and either already producing results or scheduled to start producing results within 7 days.

Open `http://localhost/` → log in → that's your dashboard. The ranker is doing its job. The Diagnostics page tells you how well.

---

## What's switched on right now

All 52 picks default to **Enabled**. No operator action is required to turn anything on. Specifically:

### Active immediately (every link suggestion benefits today)

| Pick | What it does | Where you see it |
|---|---|---|
| Semantic similarity (BGE-M3) | Finds destinations that mean the same thing as the host | Every Suggestion has a `score_semantic` field |
| Keyword match | Catches literal-phrase overlap | `score_keyword` |
| PageRank | Boosts well-linked-to destinations | `score_march_2026_pagerank` |
| HITS | Authority + hub scoring | Pre-computed daily, shows up in `score_node_affinity` |
| TrustRank | Trust propagated from seed pages | Daily refresh |
| Personalized PageRank | Topic-biased authority | Daily refresh |
| Anchor diversity | Stops the same anchor text being used too often | `score_anchor_diversity` |
| Click distance, freshness, phrase relevance, field-aware relevance, learned anchor, rare term, GA4/GSC, FR-099..105 graph signals | Every fancy ranking feature | `score_*` columns on every Suggestion |
| RRF fusion (#31) | Combines multiple ranking signals fairly | Inside the ranker — no toggle needed |
| Conformal prediction (#50) + Adaptive Conformal Inference (#52) | Confidence bands on every score | `confidence_lower_bound` / `confidence_upper_bound` |
| Uncertainty sampling (#49) | Surfaces the most-uncertain suggestions to you first | Review queue ordering |
| Elo (#35), Auto-Seeder (#51), QL Dirichlet (#28), Position-bias IPS (#33), Cascade Click (#34) | Behind-the-scenes calibration | Auto-fires when data flows |

### The 10 helpers from the Wire phase (Phase 6 picks)

These are the ones I (the AI) installed and configured this week. Each is paper-backed, defaults to on, and is wired into the pipeline:

| Pick | What it does | First real result expected |
|---|---|---|
| **VADER #22** (Hutto-Gilbert 2014) | Reads sentiment of a sentence | Immediate — scores every reviewed Suggestion |
| **PySBD #15** (Sadvilkar-Neumann 2020) | Splits text into sentences accurately | Immediate — runs on every imported page |
| **YAKE! #17** (Campos 2020) | Extracts keywords from a document | Immediate |
| **Trafilatura #7** (Barbaresi 2021) | Strips nav/footer/ads from web pages | Whenever you import a new page |
| **FastText LangID #14** (Joulin 2016) | Detects which language a text is in | Immediate |
| **LDA #18** (Blei-Ng-Jordan 2003) | Learns topic distribution per page | First model trained within 7 days |
| **KenLM #23** (Heafield 2011) | Fluency scoring (does this sentence read naturally?) | First model trained within 7 days |
| **Node2Vec #37** (Grover-Leskovec 2016) | Graph-structure embeddings | First model trained within 7 days |
| **BPR #38** (Rendle 2009) | Pairwise ranking from your approve/reject feedback | Once you have ≥ 5 reviewed Suggestions |
| **Factorization Machines #39** (Rendle 2010) | Learns interactions between ranking features | Once you have ≥ 5 reviewed Suggestions |

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
