# FR-017: GSC Search Outcome Attribution & Delayed Reward Signals

## Source and Math-Fidelity
- **Primary Source**: Google Search Console Analytics API (Search Analytics: query, page, click, impression, ctr, position).
- **Statistical Method**: 
  - **Bayesian Smoothing**: Use a Beta distribution conjugate prior ($Beta(\alpha, \beta)$) for CTR estimation to normalize low-traffic pages.
  - **Causal Lift**: Bayesian Structural Time Series (BSTS) principles for counterfactual estimation (predicting what traffic would have been without the link).
  - **Significance**: 95% Credible Intervals for lift and T-Tests for position delta significance.
- **Metric Interpretation**: Bounded delayed reward signals (positive/neutral/negative) used as ground truth for the FR-018 auto-tuning layer.

## Architecture: Python-Native Core
- **Data Ingestion (Python)**: Use `google-api-python-client` in a Celery task to pull daily performance rows.
- **Attribution Engine (Python)**: Live implementation at `backend/apps/analytics/impact_engine.py` uses `scipy.stats` (Gamma + Poisson) and `numpy` for the Bayesian causal-lift Monte Carlo. The interim 2026-Q1 C# implementation (`MathNet.Numerics` inside the `http-worker`) was decommissioned 2026-04 and is no longer authoritative.
- **Persistence (PostgreSQL)**: Shared storage in the main Django database handles the final attribution snapshots via the Django ORM.

## Implementation Spec

### 1. Backend Data Models (Django)

#### [NEW] `GSCDailyPerformance`
Stores raw daily stats from GSC.
- `id`: BigAutoField
- `page_url`: URLField (db_index=true)
- `date`: DateField (db_index=true)
- `impressions`: PositiveIntegerField
- `clicks`: PositiveIntegerField
- `avg_position`: FloatField
- `ctr`: FloatField
- `property_url`: String (the GSC property this belongs to)

#### [NEW] `GSCImpactSnapshot`
Stores the calculated attribution for a specific applied suggestion.
- `suggestion`: OneToOneField(Suggestion)
- `apply_date`: DateTimeField
- `window_type`: CharField (choices: 7d, 14d, 28d, 90d)
- `baseline_clicks`: IntegerField
- `post_clicks`: IntegerField
- `lift_clicks_pct`: FloatField
- `lift_clicks_absolute`: IntegerField
- `probability_of_uplift`: FloatField (0.0 to 1.0)
- `reward_label`: CharField (positive, neutral, negative, inconclusive)
- `last_computed_at`: DateTimeField

`GSCImpactSnapshot` is only written when the matched-control group is conclusive. The live attribution engine requires at least 3 matched controls for the same suggestion/window; if a recompute falls below that threshold, the engine withholds the snapshot and deletes any stale snapshot for that window. The UI should treat that state as "no reliable claim yet," not as positive, neutral, or negative proof.

### 2. GSC Data Importer (Python)
- **Task**: `apps.analytics.tasks.sync_gsc_performance`
- **Schedule**: Daily at 04:00 UTC (to account for the ~48h GSC processing lag).
- **Batching**: Importer looks back 5 days to ensure no gaps are left by the lag.
- **OAuth**: Google Service Account or OAuth2 token stored in `AppSetting`.

### 3. Attribution Engine Math (Python / scipy.stats)

#### Bayesian Smoothing (CTR)
To avoid high CTR noise on low impressions:
- **Prior**: Compute global site-wide CTR ($\mu_{global}$).
- **Posterior CTR**: $CTR_{smoothed} = \frac{clicks + \alpha}{impressions + \alpha + \beta}$
- Where $\alpha = \mu_{global} \times K$ and $\beta = (1 - \mu_{global}) \times K$ ($K$ is a smoothing constant, default 100).

#### Causal Lift Calculation
- **Control Group**: All pages in the same silo/scope that did *not* receive a new internal link during the window.
- **Minimum Controls**: At least 3 matched controls are required before writing a reward snapshot. Below that threshold, `ImpactReport` rows may record the inconclusive result for auditability, but no `GSCImpactSnapshot` is persisted.
- **Lift**: Calculate the relative delta $L = \frac{Post_{item}}{Baseline_{item}} - \frac{Post_{control}}{Baseline_{control}}$.
- **P-Value**: Use a two-sample T-test on daily click counts for the item vs. its own baseline, adjusted by the control group trend.

### 4. Settings & GUI (Angular)

#### GSC Settings Card
- **Inputs**: Property URL, Service Account JSON (Secure Upload).
- **Status**: Live connection badge via `searchconsole.sites().get()`.
- **Sync Control**: "Manual Backfill" button with date range picker.

#### Analytics: Search Impact Tab
- **Scatter Plot**: X-axis: Impressions, Y-axis: Lift %. Dot color = Reward Label.
- **Cohort Analysis**: Group winners by "Source Type" (XenForo vs WordPress) and "Anchor Family".
- **Table**: List of applied suggestions with their calculated reward signal.

## Test Plan
- **Mock GSC Data**: Verify the importer handles the "lag window" by merging existing rows without duplicates.
- **Statistical Unit Tests (Python)**:
  - Ensure $CTR_{smoothed}$ stays within (0,1).
  - Verify that a 0-click, 1-impression page does not get a 0% CTR (it should be pulled toward the site average).
- **Regression**: Ensure that GSC work does not block the main pipeline run if the Google API is down.

## Slices for Execution
### Slice 1: GSC Backend Models and API (Django)
- Migrations for `GSCDailyPerformance` and `GSCImpactSnapshot`.
- Serializers and basic CRUD for GSC settings.

### Slice 2: GSC Settings UI & OAuth (Angular)
- Implementation of the Settings card.
- Mock OAuth flow / Service Account credential storage.

### Slice 3: Performance Ingestion (Python)
- The Celery task for GSC sync.
- Handling the 48h lag logic.

### Slice 4: Statistical Brain (Python)
- Implement `analyze_uplift` and the Gamma-Poisson Monte Carlo in `backend/apps/analytics/impact_engine.py`.
- Wrap it in a Celery task in `backend/apps/analytics/tasks.py` so the backend can trigger attribution runs end-to-end without a separate process.

### Slice 5: Reporting UI (Angular)
- The "Search Impact" tab and Chart.js integration.
