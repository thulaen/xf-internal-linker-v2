# FR-017: GSC Search Outcome Attribution & Delayed Reward Signals

## Source and Math-Fidelity
- **Primary Source**: Google Search Console Analytics API.
- **Statistical Method**: Bayesian smoothing for low-volume CTR and T-Test for position/impression lift significance.
- **Metric Interpretation**: Bounded delayed reward signals (positive/neutral/negative) for the FR-018 auto-tuning layer.

## Implementation Spec

### 1. Backend Data Models
- **[NEW] `GSCDailyPerformance`**:
  - `page_url`: String (canonical)
  - `date`: Date
  - `impressions`: Integer
  - `clicks`: Integer
  - `sum_position`: Float (average_position * impressions, to allow re-aggregation)
  - `ctr`: Float
- **[NEW] `GSCImpactSnapshot`**:
  - `destination_url`: String
  - `suggestion_id`: UUID (FK to Suggestion)
  - `apply_date`: DateTime
  - `window_type`: Enum (7d, 28d, 90d)
  - `baseline_clicks`: Integer
  - `baseline_impressions`: Integer
  - `baseline_avg_position`: Float
  - `post_clicks`: Integer
  - `post_impressions`: Integer
  - `post_avg_position`: Float
  - `lift_clicks`: Float (%)
  - `lift_position`: Float (absolute)
  - `p_value`: Float
  - `reward_label`: String (positive, neutral, negative, inconclusive)

### 2. GSC Data Importer
- **Task**: `analytics.sync_gsc_performance`
- **Logic**:
  - Use `google-api-python-client` to fetch `query`, `page`, `impression`, `click`, `ctr`, and `position`.
  - Store results in `GSCDailyPerformance`.
  - Note: GSC data has a ~48h processing lag. Importer must look back at least 3 days.

### 3. Attribution Engine
- **Task**: `analytics.compute_search_impact`
- **Logic**:
  - Identify suggestions where `status = 'applied'`.
  - For each window (e.g., 28 days post-apply):
    - Select baseline metrics (28 days before apply_date).
    - Select post-metrics (28 days after apply_date).
    - Calculate lift: `(post - baseline) / baseline`.
    - Apply **Wilson Score** to CTR and **Bayesian Smoothing** to impressions.
    - If `lift > threshold` AND `p_value < 0.05`, mark as **positive**.

### 4. Settings & GUI
- **GSC Settings Card**:
  - Property URL (e.g., `sc-domain:example.com`)
  - Service Account Email
  - Private Key (Write-only)
  - "Test Connection" button calling `sites.get`.
- **Analytics Impact View**:
  - New tab "Search Impact".
  - Scatter plot: Suggestions (X=Impressions, Y=Lift).
  - Table of "Biggest Winners" and "Biggest Losers".

## Test Plan
- **Mock GSC API**: Verify that the importer handles the 48h lag and empty responses correctly.
- **Math Verification**: Unit tests for the Lift and P-Value calculation using static data.
- **Consistency**: Ensure a suggestion applied yesterday does not show a "Long-term (90d)" reward signal yet.
