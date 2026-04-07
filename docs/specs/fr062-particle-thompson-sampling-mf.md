# FR-062 - Particle Thompson Sampling with Matrix Factorisation

## Confirmation

- **Backlog confirmed**: `FR-062 - Particle Thompson Sampling with Matrix Factorisation` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No latent-factor explore/exploit model exists in the current system. The closest mechanism is UCB1 bandit reranking (FR-013), which treats each suggestion as an independent arm with no shared structure. FR-062 learns latent relationships between pages via matrix factorisation and uses a particle filter for Bayesian posterior tracking -- fundamentally different from independent-arm bandits.
- **Repo confirmed**: Click and approval interaction data is already stored per suggestion. The `Suggestion` model tracks approval status and, when analytics integration is active, click-through events. These interactions form the observation matrix for factorisation.

## Current Repo Map

### Explore/exploit already available

- `backend/apps/pipeline/services/ranker.py`
  - Feedback UCB reranking (FR-013) applies Upper Confidence Bound exploration bonuses to individual suggestions. Each arm is independent -- learning that page X links well to page Y tells UCB nothing about whether page Z (similar to X) would also link well to Y.

### Interaction data already available

- `backend/apps/suggestions/models.py`
  - `Suggestion.status` -- approved/rejected/pending per (source_page, destination_page) pair.
  - `Suggestion.click_count`, `Suggestion.impression_count` -- when analytics tracking is active.
  - These form a sparse binary interaction matrix: rows = source pages, columns = destination pages, values = {clicked/approved, not clicked/rejected, unobserved}.

### Embedding data already available

- `backend/apps/content/models.py`
  - `ContentItem.embedding` -- BGE-M3 1024-dim embeddings per page.
  - These provide content-based priors for cold-start pages, complementing the interaction-based latent factors.

## Source Summary

### Patent: US10332015B2 -- Particle Thompson Sampling for Online Matrix Factorisation Recommendation (Adobe, 2019)

**Plain-English description of the patent:**

The patent describes a method for making recommendations by combining matrix factorisation (learning hidden preference patterns from user-item interactions) with Thompson Sampling (exploring uncertain options to gather more data). It uses a Rao-Blackwellized Particle Filter to maintain a distribution over the latent factor matrices, updating this distribution as new interactions arrive. Each particle represents a possible "world" of user preferences, and the system samples from these particles to balance exploration and exploitation.

**Repo-safe reading:**

The patent targets user-item recommendation (movies, products). This repo targets source-page to destination-page link suggestions. The mathematical framework applies directly: pages replace users and items, interactions replace ratings, and the latent factors capture hidden "linking affinity" patterns.

**What is directly supported by the patent:**

- Rao-Blackwellized particle filter for posterior tracking over latent factor matrices;
- Thompson Sampling for explore/exploit decisions;
- online updating as new interactions arrive.

**What is adapted for this repo:**

- "users" and "items" both map to pages (symmetric factorisation);
- binary interactions (clicked/approved vs not) replace numerical ratings;
- the particle count and latent dimension are scaled down for 16GB RAM (P=30 particles, L=20 latent dims);
- content embeddings provide warm-start initialisation for cold pages.

## Plain-English Summary

Simple version first.

Imagine you run a library. You notice that readers who enjoy Book A also tend to enjoy Book X. If a new reader picks up Book B (which is similar to Book A in ways you cannot directly see), you can guess they might also enjoy Book X -- even if nobody has tried that combination yet.

The current UCB1 bandit cannot do this. It treats every source-destination pair as a completely independent experiment. If page A links well to page X, UCB1 learns nothing about whether page B (which has a similar "linking personality" to A) would also link well to X.

FR-062 solves this with matrix factorisation. It discovers hidden "linking personality" patterns -- maybe some pages are "hub-like" and link well to many destinations, or maybe certain topic combinations always work well together. These hidden patterns are represented as small vectors (latent factors) per page.

The particle filter part handles uncertainty. Instead of committing to one set of latent factors, the system maintains 30 different "guesses" (particles) about what the true factors are. When it needs to rank suggestions, it samples from these guesses -- sometimes picking an optimistic guess (exploration) and sometimes the most likely guess (exploitation). This naturally balances trying new things against sticking with what works.

## Problem Statement

UCB1 bandit reranking (FR-013) treats each link suggestion as an independent arm. This independence assumption causes two problems:

1. **Cold start**: new pages have zero interaction data. UCB1 explores them blindly with no prior. It cannot leverage the fact that a new page is similar to an existing well-understood page.
2. **No transfer learning**: learning that "tutorial pages link well to reference documentation" on page A does not help predict the same pattern on page B. Each page starts from scratch.

FR-062 addresses both by learning latent factors that capture shared structure across pages. If source page B has similar latent factors to source page A (because they interact with similar destinations), the system transfers A's knowledge to B -- even with zero direct observations for B.

## Goals

FR-062 should:

- maintain a Rao-Blackwellized particle filter with P=30 particles over latent factor matrices U and V;
- use L=20 latent dimensions per page;
- update the posterior online as new interactions (clicks, approvals, rejections) arrive;
- produce a Thompson-sampled score per (source, destination) pair that balances exploration and exploitation;
- handle cold-start pages by initialising latent factors from content embedding similarity;
- keep the score additive on top of existing ranking, off by default (weight = 0.0);
- resample particles when effective sample size drops below P/2;
- persist particle state to disk for recovery after restart;
- fit the current Django + Celery + PostgreSQL architecture within ~240 MB RAM.

## Non-Goals

FR-062 does not:

- replace UCB1 bandit reranking -- it provides a complementary explore/exploit mechanism;
- modify any content embedding or text field;
- require a GPU or real-time model serving infrastructure;
- handle multi-armed contextual bandits (the context is captured in the latent factors, not as explicit features);
- implement a full recommendation system UI;
- depend on external APIs or services;
- implement production code in the spec pass.

## Math-Fidelity Note

### Model

```text
R_{ui} ~ Bernoulli(sigma(U_i . V_j^T))
```

where:
- `R_{ui}` = binary interaction (1 = clicked/approved, 0 = not clicked/rejected)
- `U in R^{pages x L}` = source page latent factors
- `V in R^{pages x L}` = destination page latent factors
- `L = 20` (latent dimension)
- `sigma(x) = 1 / (1 + exp(-x))` (sigmoid function)

**Prior:**

```text
U_i ~ N(0, sigma_U^2 * I),  sigma_U^2 = 0.1
V_j ~ N(0, sigma_V^2 * I),  sigma_V^2 = 0.1
```

### Rao-Blackwellized Particle Filter (P=30 particles)

**Particle state:**

```text
Particles = { (U^(p), V^(p), log_w^(p)) }_{p=1..P}
```

Each particle `p` stores its own copy of the latent factor matrices and a log-weight.

**On new observation (source u, destination j, outcome r):**

```text
For each particle p:
  log_w^(p) += r * log(sigma(U_u^(p) . V_j^(p))) + (1-r) * log(1 - sigma(U_u^(p) . V_j^(p)))
```

**Weight normalisation:**

```text
w^(p) = exp(log_w^(p)) / SUM_p exp(log_w^(p))
```

**Effective sample size check:**

```text
ESS = 1 / SUM_p (w^(p))^2

If ESS < P/2:
  Systematic resample: draw new particles proportional to weights
  Perturb: add N(0, 0.01) noise to U, V of each resampled particle
  Reset all log_w^(p) = -log(P)
```

### Thompson Sampling score

For a (source u, destination j) pair:

```text
Sample one particle p* ~ Categorical(w^(1), ..., w^(P))
Score(u, j) = sigma(U_u^(p*) . V_j^(p*))
```

This naturally explores: uncertain pairs have high weight variance across particles, so different samples yield different scores, causing the system to try different rankings.

**Deterministic alternative (for diagnostics):**

```text
Score_mean(u, j) = SUM_p w^(p) * sigma(U_u^(p) . V_j^(p))
```

### Cold-start initialisation

For a new page `i` with no interaction data:

```text
U_i^(p) = alpha * PCA_L(embedding_i) + (1-alpha) * N(0, sigma_U^2 * I)
```

where `PCA_L` projects the 1024-dim content embedding to L=20 dimensions, and `alpha = 0.5` balances content prior against random initialisation.

### Score integration

```text
pts_score = Score(u, j)   [already in (0, 1) via sigmoid]
score_final += pts_mf.ranking_weight * (pts_score - 0.5)
```

Default: `ranking_weight = 0.0` -- diagnostics run silently.

### RAM budget

```text
2 matrices (U, V) * 50K pages * 20 latent dims * 30 particles * 4 bytes
= 2 * 50000 * 20 * 30 * 4 = 240 MB
```

## Scope Boundary Versus Existing Signals

FR-062 must stay separate from:

- `Feedback UCB reranking (FR-013)`
  - UCB treats arms independently with no shared structure;
  - FR-062 learns latent factors that transfer knowledge between similar pages;
  - different mathematical framework (bandit vs. matrix factorisation).

- `Semantic similarity (score_semantic)`
  - semantic similarity uses content embeddings (text-based);
  - FR-062 uses interaction-based latent factors (behaviour-based);
  - a pair can have high semantic similarity but low interaction affinity, or vice versa.

- `ListNet listwise ranking (FR-060)`
  - ListNet trains on editor labels with known features;
  - FR-062 discovers latent features from interaction data;
  - different learning paradigm (supervised vs. semi-supervised).

Hard rule: FR-062 must not modify any content embedding, any text field, or any existing signal computation. It reads interaction data and produces one additive score per pair.

## Inputs Required

FR-062 uses only data already available:

- `Suggestion.status` -- binary interaction outcome (approved/clicked = 1, rejected/not-clicked = 0)
- `Suggestion.host_content_item_id` -- source page identifier
- `Suggestion.destination_content_item_id` -- destination page identifier
- `ContentItem.embedding` -- for cold-start initialisation only

Explicitly disallowed inputs:

- raw text or tokens
- analytics aggregates (those are for FR-061)
- any signal scores (FR-062 works on raw interactions, not pre-computed scores)

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `pts_mf.enabled`
- `pts_mf.ranking_weight`
- `pts_mf.particle_count`
- `pts_mf.latent_dim`
- `pts_mf.cold_start_alpha`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `particle_count = 30`
- `latent_dim = 20`
- `cold_start_alpha = 0.5`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `10 <= particle_count <= 100`
- `5 <= latent_dim <= 50`
- `0.0 <= cold_start_alpha <= 1.0`

### Feature-flag behavior

- `enabled = false`
  - skip particle filter entirely
  - store `score_pts_mf = 0.5`
  - store `pts_mf_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - maintain particle filter and update on interactions
  - compute scores and store diagnostics
  - do not change ranking order
- `enabled = true` and no interactions yet
  - store `score_pts_mf = 0.5`
  - store `pts_mf_state = neutral_no_interactions`

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.pts_mf_diagnostics`

Required fields:

- `score_pts_mf` -- Thompson-sampled score in (0, 1)
- `score_pts_mf_mean` -- weighted mean score across all particles (deterministic)
- `pts_mf_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_no_interactions`
  - `neutral_cold_start`
  - `neutral_processing_error`
- `source_interaction_count` -- how many interactions the source page has
- `destination_interaction_count` -- how many interactions the destination page has
- `effective_sample_size` -- current ESS of the particle filter
- `last_resample_timestamp` -- when particles were last resampled
- `exploration_variance` -- variance of scores across particles (high = uncertain = more exploration)

Plain-English review helper text should say:

- `PTS-MF score reflects how well this source-destination pair matches hidden interaction patterns learned from past approvals and clicks.`
- `High exploration variance means the system is uncertain about this pair and may rank it differently on the next run.`
- `Cold start means this page is new and the score is based on content similarity rather than interaction data.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_pts_mf: FloatField(default=0.5)`
- `pts_mf_diagnostics: JSONField(default=dict, blank=True)`

### Particle state storage

- Particle matrices serialised to `backend/ml_models/pts_mf_state.npz` (NumPy compressed)
- File size: ~240 MB (matches RAM footprint)
- Backed up before each update for rollback

### PipelineRun snapshot

Add FR-062 settings and particle filter state summary to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/pts-mf/`
- `PUT /api/settings/pts-mf/`
- `POST /api/settings/pts-mf/reset/` -- reinitialises particle filter from scratch

### Review / admin / frontend

Add one new review row:

- `PTS-MF Score`

Add one small diagnostics block:

- Thompson-sampled score and mean score
- exploration variance
- interaction counts for source and destination
- cold-start indicator

Add one settings card:

- enabled toggle
- ranking weight slider
- particle count input
- latent dimension input
- cold-start alpha slider
- reset button (with confirmation)

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/pts_mf.py` -- new service file (particle filter + MF)
- `backend/apps/pipeline/services/ranker.py` -- add FR-062 additive hook
- `backend/apps/pipeline/tasks.py` -- particle state persistence task
- `backend/apps/suggestions/models.py` -- add two new fields
- `backend/apps/suggestions/serializers.py` -- expose new fields
- `backend/apps/suggestions/views.py` -- snapshot FR-062 settings
- `backend/apps/suggestions/admin.py` -- expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` -- add settings endpoint
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-062 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched:

- `backend/apps/content/models.py` -- no new content fields (embeddings read only)
- `backend/apps/graph/models.py`
- All individual signal computation files

## Test Plan

### 1. Particle filter initialisation

- P=30 particles initialised with correct dimensions
- all log weights start equal at -log(P)
- cold-start pages get PCA-projected embedding initialisation

### 2. Observation update

- positive observation increases weight of particles where source-dest dot product is high
- negative observation increases weight of particles where source-dest dot product is low
- log weights remain finite (no NaN or Inf)

### 3. Resampling

- ESS drops below P/2 -> systematic resample triggers
- after resample, all weights reset to -log(P)
- particles are perturbed after resample (not identical copies)

### 4. Thompson Sampling

- sampling different particles produces different scores for the same pair
- mean score is deterministic for the same particle state

### 5. Neutral fallback cases

- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`
- no interactions -> `score = 0.5`, state `neutral_no_interactions`

### 6. RAM budget

- with P=30, L=20, 50K pages: total particle state < 250 MB

### 7. Isolation

- updating particle state does not modify any content embedding
- FR-062 scores do not affect any other signal computation

### 8. State persistence

- particle state saved to disk and restored correctly after restart
- corrupted state file -> reinitialise from scratch with warning

## Rollout Plan

### Step 1 -- passive observation

- enable particle filter with `ranking_weight = 0.0`
- let the filter accumulate observations for 2-4 weeks
- inspect exploration variance and score distributions

### Step 2 -- quality validation

- compare PTS-MF scores against editor approval rates
- verify that high PTS-MF scores correlate with approval
- check cold-start behaviour for new pages

### Step 3 -- optional ranking enablement

- only after correlation is confirmed
- recommended first live weight: `0.02` to `0.04`

## Risk List

- 240 MB RAM is significant on 16 GB -- mitigated by keeping L=20 and P=30, with configuration to reduce further;
- particle degeneracy (all weight concentrates on one particle) -- mitigated by systematic resampling with perturbation;
- cold-start initialisation from embeddings may not correlate well with interaction patterns -- mitigated by `cold_start_alpha = 0.5` which blends embedding prior with random initialisation;
- interaction data may be sparse for low-traffic sites -- mitigated by neutral fallback and the `neutral_no_interactions` state;
- sigmoid saturation on large dot products -- mitigated by the prior variance `sigma^2 = 0.1` which keeps latent factors small.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"pts_mf.enabled": "true",
"pts_mf.ranking_weight": "0.03",
"pts_mf.particle_count": "30",
"pts_mf.latent_dim": "20",
"pts_mf.cold_start_alpha": "0.5",
```

**Why these values:**

- `enabled = true` -- start accumulating observations from day one.
- `ranking_weight = 0.03` -- conservative; PTS-MF is the most complex model and needs thorough validation before significant ranking impact.
- `particle_count = 30` -- good balance between posterior approximation quality and RAM usage.
- `latent_dim = 20` -- sufficient to capture major interaction patterns without overfitting.
- `cold_start_alpha = 0.5` -- equal blend of content prior and random initialisation.

### Migration note

FR-062 must ship a new data migration that upserts these five keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
