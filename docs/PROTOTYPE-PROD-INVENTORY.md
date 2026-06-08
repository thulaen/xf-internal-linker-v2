# Production Feature & Option Inventory — XF Internal Linker V2

This is the definitive, deduplicated master checklist compiled from six domain audits of the live codebase. Every name below is taken verbatim from production source. The prototype must satisfy this list.

---

## 1. NAVIGATION / INFORMATION ARCHITECTURE

### Sidebar (`app.component.ts navSections`)

**MAIN**
- Dashboard (`/dashboard`) — icon `dashboard`

**ANALYSIS**
- Review (`/review`) — icon `rate_review`, badge: pending suggestion count
- Link Health (`/link-health`) — icon `link_off`, badge: open broken links
- Link Graph (`/graph`) — icon `account_tree`
- Behavioral Hubs (`/behavioral-hubs`) — icon `hub`
- Analytics (`/analytics`) — icon `bar_chart`
- Embeddings (`/embeddings`) — icon `compare_arrows`

**SYSTEM**
- Jobs (`/jobs`) — icon `pending_actions`
- System Health (`/health`) — icon `health_and_safety`
- AI Agents (`/mcp`) — icon `extension`
- Monthly Reports (`/reports/monthly`) — icon `event_note`
- Settings (`/settings`) — icon `settings`
- Alerts (`/alerts`) — icon `notifications`
- Scheduled Updates (`/scheduled-updates`) — icon `schedule`
- Web Crawler (`/crawler`) — icon `travel_explore`
- Error Log (`/error-log`) — icon `bug_report`, badge: unacknowledged error count
- Performance (`/performance`) — icon `speed`
- Find Bugs (`/find-bugs`) — icon `pest_control`
- Observability (`/observability`) — icon `insights`
- Work Queue (`/work-queue`) — icon `assignment`
- Operations Feed (`/operations-feed`) — icon `rss_feed`
- Preferences (`/preferences`) — icon `tune`
- Models (`/admin/models`) — icon `developer_board`
- Undo History (`/audit/undo-timeline`) — icon `restore`

### Navigation chrome
- Breadcrumbs (auto-hide if route < 3 levels deep)
- Skip to Main Content (hidden, Tab reveals)
- Nav Progress Bar (route change)
- Offline Banner (sticky, self-hides)
- Scroll-to-Top Button (if enabled)
- Recent Pages Menu (last 5 visited, auto-hides empty)
- Freshness Ribbon: Sync badge (stale >48h), Analytics badge (stale >72h), Pipeline badge (stale >336h), Runtime Mode chip (CPU | GPU)

---

## 2. GLOBAL TOOLBAR & MODES

### Core indicators
- **Pulse Indicator** (system status): live | degraded | down | unknown; shows task count
- **Performance Mode chip**: Balanced | Safe | High Performance (icons balance | shield | speed) → `/dashboard#performance-mode`
- **Master Pause button**: ON (paused) | OFF (running)
- **System Health status dot**: healthy | degraded | critical | unknown (menu: banner, total services, issues count, last check, link to `/health`)
- **WebSocket status pill**: connected | reconnecting | offline
- **Presence Indicator** (online users, same-route presence)
- **Notification Center** toggle

### Learning & help modes
- **Tutorial Mode** toggle (icon `school`)
- **Explain Mode** toggle (icon `help_outline`)
- **Noob/Pro Mode** toggle (noob | pro; icons `sentiment_satisfied` | `engineering`)
- **Glossary** drawer (Alt+G, icon `menu_book`)
- **Replay Dashboard Tour** (icon `tour`)
- **FAQ** drawer (icon `contact_support`)
- **Suggest a Feature** dialog (icon `lightbulb`, 520px)

### Admin & user
- **Admin Panel** (Django Admin, new tab)
- **User Menu**: username, email, Admin Panel link, Sign out

### Keyboard shortcuts
- Ctrl+K / Cmd+K — Command Palette
- ? — keyboard shortcut cheatsheet
- Alt+G — glossary drawer
- Shift+D — debug overlay

### Global overlays
- Glossary Drawer, FAQ Drawer, Guided Tour, Escape Hatch FAB (bottom-left), Help Chatbot FAB (bottom-right), Debug Overlay, Command Palette

---

## 3. ACCESSIBILITY & APPEARANCE

### Accessibility menu (`a11yMenu`, A11yPrefsService)
- **High Contrast**: On | Off (default normal)
- **Font Size**: 90% · 100% · 115% · 130% (default 100)
- **Dyslexia-Friendly Font**: On | Off (default system)
- **Colour-Blind Palette**: Off | Protan | Deutan | Tritan (default none)
- **Reset to Defaults**

### Customize Appearance drawer (ThemeCustomizerComponent / AppearanceService)
- **Colors**: Primary (default `#4285f4`), Accent (`#4285f4`), Header background (`#ffffff`)
- **Typography → Font size**: Small (13px) · Medium (13px) · Large (16px) — default small
- **Layout → Content width**: Narrow (960px) · Standard (1280px) · Wide (full) — default wide
- **Layout → Sidebar width**: Compact (200px) · Standard (220px) · Comfortable (260px) — default standard
- **Layout → Density**: Compact · Comfortable — default comfortable
- **Site Identity**: Site name (default "XF Internal Linker"), Logo upload (PNG/SVG/WEBP/JPEG ≤2MB), Favicon upload (PNG/SVG/ICO ≤2MB)
- **Footer**: Show footer (default true), Footer text (default "XF Internal Linker V2"), Footer background (`#ffffff`)
- **Scroll to Top**: Show button (default true)
- **Presets**: Load · Save current as preset · Delete · Reset to defaults

> Note: Preferences page (`/preferences`) also aggregates appearance, language, accessibility, onboarding.

---

## 4. DASHBOARD (`/dashboard`)

### Primary controls
- Run Pipeline · Import Data (→ Jobs) · Sync Now · Emergency Stop
- Quick Search Bar (sticky)
- Dashboard Mode Toggles — Performance Mode: balanced (default) | fast | calm; Runtime Mode display: cpu | gpu
- Metric Ticker (active issues chip)

### Summary cards (GSC)
- Review Queue: Pending | Approved | Applied | Total
- Content & Sync: Content items | Open broken links | Last sync items
- System Health: status (healthy/degraded) | monitored services
- Latest Pipeline Run: Suggestions created | Destinations processed

### Status tabs
Pending · Approved · Rejected · Applied · All

### Sections / widgets
- Attention Banner (single CTA → health/link-health/review)
- Right Now: Mission Brief, Priority Summary Bell, Status Story, Priority Action Queue, Health Score Dial, Trend Deltas
- Operating Desk: Ready to Run, Performance Mode card, Runtime Mode, What Changed, Today Focus, Pick Up (resume), Running Now, Ranking Strategy
- Setup Checklist (first run): Connect forum · Import content · Run pipeline · Review suggestions
- Recent Data: Recent Pipeline Runs table (Run ID, State, Suggestions, Destinations, Duration, Started), Recent Imports, Webhook Log, Activity Feed
- Statistics Grid: Open broken links · Pending review · Approved · Applied live links · Content items
- Learning Cluster: Command Suggestions ("I want to…"), Task-to-Page Router, Color Legend, Daily Quiz
- Help & Admin Cluster: One-Button Reset, Tips of Day, Weekly Digest Optin
- Extras: Instant Health, Launcher Grid, Goal Tracker, Sync Activity, Schedule Widget, Rotating Cards (Wins/Avoids/Pitfalls/Quotes), ELI5 Card, Flow Diagram, Quiet Hours Indicator, Who's On Shift, What's New, RUM Summary, Confidence Meter ("Ready to Rock")

---

## 5. REVIEW (`/review`)
- **Status tabs**: Pending · Approved · Rejected · Applied · All
- **Filters**: Search; Sort By (Score high→low · Score low→high · Newest first · Oldest first); Same silo only (checkbox)
- **Card fields**: status pill, score chip (high/medium/low), repeated-anchor warning, needs-review badge, aging indicator, date created, target destination (+silo), source content (+silo), host sentence (anchor highlight), anchor text + confidence badge, SEO risk indicators
- **Card actions**: Approve, Reject (→ rejection-reason menu), Open full details
- **Batch bar**: Select all, Approve All, Reject All (→ reasons), Clear selection
- **Pagination**: 25/page

---

## 6. LINK HEALTH (`/link-health`)
- **Summary cards**: Open · Ignored · Fixed
- **Filters**: Status chips (All · Open · Ignored · Fixed); HTTP Status (All · Connection error 0 · 301 · 302 · 403 · 404 · 410)
- **Actions**: Scan Now, Export CSV
- **Scan progress**: bar + job ID + message (WebSocket + polling)
- **Table**: Source thread · URL (redirect hint) · HTTP status · Status chip · First detected · Actions (Mark Fixed · Ignore · Open source thread)

---

## 7. LINK GRAPH (`/graph`) — 10 tabs
1. **Overview** — statistics
2. **Topics** — SiloGroup summaries
3. **Entities** — type filter (All · Keyword · Named Entity · Topic Tag), search; table: Canonical Form, Entity Type, Article Count
4. **Hub Articles** — table: Title, Content Type, PageRank Score (March 2026 PageRank)
5. **Audits** — mode toggle (Orphan · Low Authority); table: Title, Scope, Inbound Links, PageRank, Actions (Suggest Links · Focus in Graph); Export CSV
6. **Network Visualization** (D3) — Heatmap toggle, History Mode + date picker, node details, Context filter (All · Contextual only)
7. **Path Explorer** — From/To autocomplete, Find Path, path result
8. **Freshness** — velocity chart (created/disappeared), churn table
9. **Coverage Gaps** — gap threshold slider (default 0.8), Reload, gaps overlay toggle, gap nodes table (Title, Inbound, Pending Suggestions, Neglect Score), ghost-edge quick-approve
10. **Qualities** — context pie, anchor frequency bar, anchor warnings table, page quality rows, isolated links table

---

## 8. ANALYTICS (`/analytics`)
- **Engagement window**: 7 · 14 · 30 days (persisted)
- **Top Suggestions order**: Clicks · Quick Exit (persisted)
- **Source filter**: Combined · GA4 only · Matomo only
- **Search Impact**: window selector 7d · 28d · 90d, scatter chart (Baseline Clicks vs Lift %), cohort by source, cohort by anchor family
- **Search Outcome**: Funnel (Impressions→Clicks→Views→Engaged→Conversions), Trend chart, version comparison, device doughnut, channel doughnut, geographic mix (top 10 countries)
- **Integrations card**: GA4 status + test, Matomo status + test, browser snippet copy, Run GA4 Sync, Run Matomo Sync
- **Health Summary**: coverage badges

---

## 9. EMBEDDINGS (`/embeddings`)

### Tabs
Overview · Providers · Settings · Bake-off · Audit

### Providers & models
- **OpenAI** (`openai`, tokenizer `cl100k_base`, batch ceiling 2048):
  - `text-embedding-3-small` — 1536 dim, 8191 tok, $0.00002/1K — **DEFAULT**
  - `text-embedding-3-large` — 3072 dim, 8191 tok, $0.00013/1K
  - `text-embedding-ada-002` — 1536 dim, 8191 tok, $0.00010/1K
- **Gemini** (`gemini`, char-heuristic tokenizer, batch ceiling 100):
  - `text-embedding-004` — 768 dim, 2048 tok, $0.000025/1K — **DEFAULT**
  - `gemini-embedding-exp-03-07` — 3072 dim, 2048 tok, $0.00013/1K

### Config (AppSetting keys, with defaults)
- Routing: `embedding.provider` (openai), `embedding.fallback_provider` (openai), `embedding.recommended_provider` ("")
- Model: `embedding.model` (text-embedding-3-small), `embedding.api_key` (secret), `embedding.api_base` (""), `embedding.dimensions_override` ("")
- Rate/cost: `embedding.rate_limit_rpm` (3000), `embedding.rate_limit_tpm` (1000000), `embedding.monthly_budget_usd` (50.0), `embedding.timeout_seconds` (30), `embedding.max_retries` (5)
- Quality gate: `embedding.gate_enabled` (true), `embedding.gate_quality_delta_threshold` (-0.05), `embedding.gate_noop_cosine_threshold` (0.9999), `embedding.gate_stability_threshold` (0.99), `embedding.provider_ranking_json` ({})
- Audit: `embedding.accuracy_check_enabled` (true), `embedding.audit_resample_size` (50), `embedding.audit_norm_tolerance` (0.02), `embedding.audit_drift_threshold` (0.9999), `embedding.accuracy_last_run_at` ("")
- Bake-off: `embedding.bakeoff_enabled` (true), `embedding.bakeoff_sample_size` (1000), `embedding.bakeoff_cost_cap_usd` (5.0)
- Hardware: `performance.profile_override` (low · medium · high · workstation; empty=auto)

### Batch / limits
- Batch size: min 8 · default 32 · max 128 (high mode 128); key `system.embedding_batch_size`
- Vector dim cap 16000; max embed text 1,000,000 chars

### Bake-off result columns
provider · mrr_at_10 · ndcg_at_10 · recall_at_10 · separation_score · cost_usd · latency_ms_p95 · created_at

### Gate decision columns
created_at · item_kind · item_id · action (REPLACE · REJECT · NOOP · ACCEPT_NEW) · reason · score_delta

---

## 10. SETTINGS (`/settings`) — 9 tabs

Overview header stats: Live features on · Recommended still off · Silo groups · Assigned scopes.

### TAB 1 — Ranking Weights
Each signal card has Enable/ranking_weight (range 0–0.3 unless noted) plus params. All defaults from code:

- **Weighted Authority (PageRank)** — weight 0.1; position_bias 0.5, empty_anchor_factor 0.6, bare_url_factor 0.35, weak_context_factor 0.75, isolated_context_factor 0.45
- **Link Freshness** — weight 0.05; recent_window_days 30, newest_peer_percent 0.25, min_peer_count 3, w_recent 0.35, w_growth 0.35, w_cohort 0.2, w_loss 0.1
- **Phrase Matching** — weight 0.08; enable_anchor_expansion ON, enable_partial_matching ON, context_window_tokens 8
- **Learned Anchors** — weight 0.05; minimum_anchor_sources 2, minimum_family_support_share 0.15, enable_noise_filter ON
- **Rare-Term Propagation** — enabled ON, weight 0.05; max_document_frequency 3, minimum_supporting_related_pages 2
- **Field-Aware Relevance** — weight 0.1; title 0.3, heading 0.15, intro 0.2, body 0.15, scope 0.1, learned_anchor 0.1
- **Click Distance** — weight 0.07; k_cd 4, b_cd 0.75, b_ud 0.25 (recalc button)
- **Spam Guards** — max_existing_links_per_host 3, max_anchor_words 4, paragraph_window 3
- **Anchor Diversity** — enabled ON, weight 0.03; min_history_count 3, max_exact_match_share 0.4, max_exact_match_count 3, hard_cap_enabled OFF
- **Keyword Stuffing** — enabled ON, weight 0.04; alpha 6.0, tau 0.3, dirichlet_mu 2000, top_k_stuff_terms 5
- **Link-Farm Detection** — enabled ON, weight 0.03; min_scc_size 3, density_threshold 0.6, lambda 0.8
- **DARB** — enabled ON, weight 0.04; out_degree_saturation 5, min_host_value 0.5
- **KMIG** — enabled ON, weight 0.05; attenuation 0.5, max_hops 2
- **TAPB** — enabled ON, weight 0.03; apply_to_articulation_node_only ON
- **KCIB** — enabled ON, weight 0.03; min_kcore_spread 1
- **BERP** — enabled ON, weight 0.04; min_component_size 5
- **HGTE** — enabled ON, weight 0.04; min_host_out_degree 3
- **RSQVA** — enabled ON, weight 0.05; min_queries_per_page 5, min_query_clicks 1, max_vocab_size 10000
- **Feedback Reranking (Explore-Exploit)** — enabled ON, weight 0.08; exploration_rate 1.41421356237
- **Near-Duplicate Clustering** — enabled ON, weight; similarity_threshold 0.04, suppression_penalty 20 (recalc button)
- **Slate Diversity** — enabled ON; diversity_lambda 0.65, score_window 0.30, similarity_cap 0.90
- **Graph Candidate Generation** — enabled ON; walk_steps_per_entity 2000, min_stable_candidates 50, min_visit_threshold 4, top_k_candidates 100, top_n_entities_per_article 15 (rebuild button)
- **Value Model Scoring** — enabled ON; w_relevance 0.35, w_traffic 0.25, w_freshness 0.1, w_authority 0.1, w_penalty 0.5, traffic_lookback_days 90, traffic_fallback_value 0.5
  - Engagement signal ON: w_engagement 0.08, lookback 30, words_per_minute 200, cap_ratio 1.5, fallback 0.5
  - Hot decay ON: hot_gravity 0.05, hot_clicks_weight 1.0, hot_impressions_weight 0.05, hot_lookback_days 90
  - Co-occurrence ON: w_cooccurrence 0.12, fallback 0.5, min_co_sessions 5
- **Phase 6 Optional Picks** (10 toggles, default ON): VADER Sentiment · PySBD Segmenter · YAKE Keywords · Trafilatura Extractor · FastText Language ID · LDA · KenLM · Node2Vec · BPR · Factorization Machines
- **Stage-1 Candidate Retrievers** (default OFF): Lexical Retriever · Query Expansion Retriever · XenForo BM25 Retriever
- **Anchor garbage signals** (preset): generic_anchor_matcher · anchor_descriptiveness · anchor_self_information
- **Graph signals** (preset): hits_authority · personalized_pagerank · trustrank (+ TrustRank auto-seeder: candidate_pool_size, seed_count_k, post_quality_min, readability_grade_max, spam_content_value_floor)
- Search Console teaser (status pill → Connect & Sync tab)

### TAB 2 — Silo Architecture
- **Silo Mode**: Disabled · Prefer same silo (default) · Strict same silo
- Same Silo Boost 0.10, Cross Silo Penalty 0.10
- Silo Groups CRUD (name, slug, description, display_order)
- Scope Assignments (assign scopes, view counts)

### TAB 3 — Connect & Sync
- **XenForo**: Forum URL, API Key, health pill (healthy/warning/error/down/stale); Test Connection, Save
- **WordPress**: Site URL, Username, App Password, Enable auto-sync, Sync Hour UTC (default 3), Sync Minute (default 0), health pill; Test Connection, Clear Password, Run Manual Sync Now
- **Crawler Settings**: Rate req/sec (1–10, default 4), Max Depth (1–10, default 5); URL Exclusion Patterns chips (defaults: /members/, /login/, /register/, /account/, /search/, /admin.php, /help/); Data Retention read-only (prune every 4 weeks, pages >90d deleted, 3× 404 = dead, fixed links archived 30d)
- **Webhook Endpoints**: XenForo Receiver URL (readonly), WordPress Receiver URL (readonly), XenForo Webhook Secret, WordPress Webhook Secret; Test Webhook Endpoints, Save
- **Google Connection**: OAuth Client ID, OAuth Client Secret, status pill, Last Synced, Redirect URI (readonly); Save Google App, Sign in with Google / Reconnect / Disconnect
- **GA4 Telemetry**: Enable browser events (default OFF), GA4 Property ID, Measurement ID, API Secret; Service Account fallback (Enable GA4 sync, Read project ID, Read client email, Read private key); Telemetry rules: Sync lookback days (1–30, default 7), Geo granularity (Do not store geography · Country only · Country and region), Event schema (default fr016_v1), Retention days (1–800, default 400), Impression visible ratio (0.25–1, default 0.5, step 0.05), Impression time ms (250–5000, default 1000, step 50), Engaged seconds (5–60, default 10); Test Browser Events, Test Read Access, Save
- **Matomo Telemetry**: Matomo URL, XenForo Site ID, WordPress Site ID, Token Auth, Enable Matomo collection (OFF), Enable Matomo sync (OFF), Sync lookback days (1–30, default 7), status pill, Last Sync; Test Connection, Save
- **Google Search Console**: Property URL, Service Account Email + Private Key (fallback), Enable Daily Sync, Lookback days (1–90), Ranking weight (0–0.3, default 0.05), Last Performance Sync, One-Time Cleanup Backfill (Backfill Days 1–365, default 180), health pill, Traffic Filter (China, Singapore excluded); Save GSC Settings, Test Connection, Manual Backfill

### TAB 4 — Library & History
- Weight Presets: Load preset dropdown, Apply, active-preset label ("Custom live mix" if no match)
- Weight Adjustment History table (date, user, preset, weights)
- Ranking Challengers table (model, status, improvement %, Promote/Reject)
- Save as Preset (name, Save)

### TAB 5 — Notifications
- **Alert Delivery**: Show Toast (ON) + Min Severity (Info · Success · Warning [default] · Error · Urgent); Desktop Popup (ON) + Min Severity + Grant Permission; Sound Cues (ON) + Min Severity (default Error)
- **Quiet Hours**: Enable (OFF), Start (22:00), End (07:00)
- **Event Subscriptions** (all ON): Job Completed · Job Failed · Job Stalled · Embedding Model Status Changes · GSC Demand Spikes
- **Test Alert**: Send Test Warning · Error · Urgent
- Save Delivery / Save Quiet Hours / Save Subscriptions

### TAB 6 — Diagnostics
- Weight Diagnostics table (Name · Weight · Rust · Storage · Health) + Refresh

### TAB 7 — Performance
- Runtime Profile Recommendation (CPU cores, RAM GB, Disk free GB, native kernels) + Apply Suggested Limits
- Model Runtime: Champion card (Pause · Resume · Drain · Rollback), Candidate card (Download · Warm · Pause · Resume · Drain · Promote), Hot Swap, Backfill panel
- Register New Model: name, family, dimension, batch size, Device (CPU), Role (Candidate · Retired), Executor (Primary · Helper), Helper node; Register Model Candidate
- Placements & Reclaimable Disk (Delete Old Placement)
- Runtime Audit Log
- Performance Tunables: Embedding Batch Size slider (default 32), CPU Encoding Threads (1–10, default 4), Default Queue Concurrency (1–6, default 2; restart req), Aggressive OOM Backoff (ON); Save / Discard

### TAB 8 — Helpers
- Summary: Online · Busy · Stale · Offline counts
- Register Helper: Name, Token, Role (Worker · Crawler), Time Policy (Anytime · Nighttime · Maintenance window), Max Concurrency (default 2), CPU Cap % (10–100, default 60), RAM Cap % (10–100, default 60), Accepting Work (Yes · No); Register Helper
- Helper cards: status dot (online/busy/stale/offline), role chip, accepting-work chip, last heartbeat, metric pills (Jobs, CPU, RAM, Network RTT, Native kernels), metadata (capabilities, queues, job lanes, warmed models, policy); Pause/Resume Intake, Remove Helper

### TAB 9 — Meta Algorithms
- Controls: Search (name/META code/family), Status filter (Active · Inactive · All), Refresh
- Per-row: Enable/Disable toggle, Name (META-NN), Family chip, Status (Winner · Alternate · Experimental), View Spec, Edit settings
- Also surfaced: family summaries (active/forward/disabled/total), Actions (Run · View Spec · Operations Feed · Mission Critical), Status values (active · forward-declared · disabled-pending-implementation · disabled)

### Settings global
- Fragment routing (#ranking-weights, #silo-architecture, …)
- Per-card save (no global Save All); Unsaved Changes guard (isDirty)

---

## 11. RANKING WEIGHTS, PRESETS, META-ALGORITHMS, AUTOTUNERS (backend)

### Core blend weights (FR-018, sum to 1.0, L-BFGS-B tuned, floor 0.01, ±5% drift/run, 90-day lookback)
- `w_semantic` 0.40 · `w_keyword` 0.25 · `w_node` 0.20 · `w_quality` 0.15
- `w_embedding_age` 0.05 (FR-249, conditional on `pipeline.embedding_age_weight_in_composite` > 0)

### Meta-algorithm parameters (FR-018b, with ranges)
- `pipeline.rrf_k` 60 [20–200], `pipeline.bm25_k1` 1.2 [0.5–3.0], `pipeline.bm25_b` 0.75 [0.05–1.0]
- `pipeline.stage1_mmr_lambda` 0.65 [0.05–0.95], `pipeline.stage1_top_k` 200 [10–500], `pipeline.stage2_top_k` 20 [1–100], `pipeline.stage1_overfetch_multiplier` 1.5 [1.0–5.0], `pipeline.min_semantic_score` 0.20 [0.10–0.50]
- `slate_diversity.similarity_cap` 0.90, `slate_diversity.diversity_lambda` 0.65
- `click_distance.k_cd` 4.0 [1.0–10.0]
- `explore_exploit.exploration_rate` 1.41421356237 [0.1–3.0]
- `field_aware_relevance.*` (title 0.30, heading 0.15, intro 0.20, body 0.15, scope 0.10, learned_anchor 0.10)
- `clustering.similarity_threshold` 0.04 [0.01–0.50]
- Not tuned: `pipeline.embedding_age_half_life_days` 365, `pipeline.nrt_delta_max_size` 10000, `pipeline.nrt_delta_refresh_seconds` 60, `pipeline.calibration_validation_set_min_size` 500, `pipeline.embedding_block_size` 256, `pipeline.cpp_path_alert_threshold` 0.05

### Preset system
- System preset: **"Recommended"** (read-only, is_system, ~100+ keys, fallback source). Custom presets apply non-destructively (only listed keys written).

### 39 active meta-algorithms (META-01…META-39)
- Optimizers/embeddings: 01 SGD · 02 Momentum · 03 AdaGrad · 04 RMSprop · 34 Adam · 05 Embeddings (paid CPU provider — see [`docs/specs/fr-cpu-paid-embeddings-runtime.md`](specs/fr-cpu-paid-embeddings-runtime.md); was BGE-M3)
- Graph/authority: 06 PageRank · 15 Link freshness · 17 Weighted destination authority · 19 Scope tree proximity · 27 Session cooccurrence · 28 Behavioral hubs · 29 Knowledge graph · 39 Graph candidate
- Retrieval/scoring: 07 Cosine top-k · 08 Tokeniser · 09 BM25 · 10 TF-IDF · 11 Keyword Jaccard · 12 Cosine similarity
- Ranking/rerank: 13 Slate diversity (MMR) · 14 Feedback reranker (Rust kernel — the old META-24 Python fallback is retired now that Rust is authoritative) · 35 Ranking challenger · 36 Explore/exploit · 38 Near-duplicate clustering
- Content/anchor: 16 Click distance · 18 Phrase match · 20 Host post quality · 21 Learned anchor · 22 Rare-term propagation · 23 Field-aware relevance · 25 Spam guard · 37 Silo leakage guard
- Value/attribution: 26 Value model · 30 Attribution engine · 31 Weight tuner (monthly) · 32 Impact engine · 33 Crawler discovery
- Forward-declared: P1–P12, Q1–Q24

### Autotuner tasks & APIs
- Tasks: `pipeline.monthly_weight_tune`, `pipeline.evaluate_weight_challenger` (SPRT), `pipeline.monthly_meta_tune`, `pipeline.evaluate_meta_challenger`, `pipeline.check_weight_rollback` (GSC clicks ratio <0.85 → rollback, min 50 pre-clicks), `pipeline.check_gsc_spikes` (1-day cooldown)
- APIs: `POST /api/weight-presets/`, `POST /api/weight-presets/{id}/apply/`, `POST /api/weight-adjustment-history/{id}/rollback/`, `GET /api/weight-adjustment-history/` (source: auto_tune/manual/preset_applied), `POST /api/ranking-challengers/{id}/reject/`, `GET|POST /api/meta-algorithms/`, `POST /api/meta-algorithms/{id}/toggle/`

---

## 12. CRAWLER (`/crawler`)
- **Controls**: Domain selector, Rate req/sec (1–10, default 4), Max Depth (1–10, default 5)
- **Session actions**: Start Crawl · Pause · Resume
- **Sitemap management**: Domain, Sitemap URL, Add, Remove
- **Session status**: Pages Crawled · New Discoveries · Changed Pages · Broken Links Found · Downloaded (bytes) · Duration · progress bar (0–1)
- **Result tabs**:
  1. Overview (session summary)
  2. Storage (20 GB cap, 90-day prune rules)
  3. Internal Links (Source URL · Destination URL · Anchor Text · Context: content/nav/sidebar/footer/breadcrumb/unknown)
  4. Broken Links (→ Link Health)
  5. SEO Audit (12 metrics: Missing Titles, Duplicate Titles, Missing Meta Descriptions, Missing H1, Multiple H1s, Missing Canonicals, Noindexed Pages, Thin Content <200 words, Slow Pages >2s, Non-Mobile, Images Missing Alt, Missing OG Tags)
  6. History (Domain · Status [pending/running/paused/completed/failed] · Pages Crawled · Duration · Date)
- **Backend session config (frozen)**: rate_limit, max_depth, max_pages (not in UI), excluded_paths, timeout_hours (2)
- **Thresholds**: THIN_CONTENT_WORD_LIMIT 200, SLOW_PAGE_MS_THRESHOLD 2000
- **Crawl create API** (`POST /crawler/sessions/`): site_domain (required), rate_limit, max_depth; pause/resume actions

---

## 13. CONTENT SYNC — WordPress & XenForo connect

### SyncJob model
- Status: pending · running · paused · completed · failed · cancelled
- Source: api (XenForo) · jsonl (JSONL File) · wp (WordPress API)
- Mode: full · titles · quick
- Progress: progress (0–1), message, items_synced, items_updated, ml_items_queued/completed, spacy_items_completed, embedding_items_completed
- Resume: checkpoint_stage, checkpoint_last_item_id, checkpoint_items_processed, is_resumable

### WebhookReceipt
- Source: api · jsonl · wp; event_type; status: received · processed · ignored · error; dedupe_key, occurrence_count, last_seen_at

### XenForo API client endpoints
verify_api_key, get_threads(node_id, page), get_thread, get_posts(thread_id, page), get_post, get_resources(category_id, page), get_resource_updates

### WordPress API client
- Auth: base_url, username, app_password
- Endpoints: verify_credentials → {ok, display_name}, get_posts/get_pages (status='publish', after), get_post/get_page, iter_posts/iter_pages
- Statuses fetched: publish (always), private (if authenticated); pagination 100/page

### Crawler sync models (content-discovery side)
- SitemapConfig: domain, sitemap_url, normalized_url, discovery_method (manual · auto), is_enabled, last_fetch_at, last_url_count, last_error
- CrawledPageMeta, CrawledLink, CrawlSession fields per crawler section above

---

## 14. JOBS (`/jobs`)
- **Import Mode**: Full import (recommended first time) · Titles only (fast refresh) · Quick check (fastest)
- **Tabs**: API source · WordPress · JSONL upload
- **Per-source view**: state (idle/uploading/running/paused/completed/failed), progress bars (ingest, ML, spaCy, embedding), message, error, Resume/Pause/Cancel
- **Sync Jobs table**: Created · Source (api/wp) · Mode · Status · Progress % · Duration · Success rate · Actions (View/Cancel)
- **Scheduling Policy card** (next sync schedule)

---

## 15. SYSTEM HEALTH (`/health`)
- Summary counts: Healthy · Warning/Stale · Error/Down · Not Configured/Not Enabled
- Service group tabs: Required to Run · Required for Sync · Required for Analytics · Optional
- Service cards: name + status badge, message, per-service Refresh, info tooltip
- Checklist groups: Infrastructure · AI & Models · Analytics Credentials · Content Sources · Web Crawler · Features · Dev Tools
- Active jobs monitoring; Disk usage % bar; GPU memory (if available)

---

## 16. MODELS (`/admin/models`)
- ML model registry — actions: Pause · Resume · Promote · Drain · Rollback
- Champion / Candidate cards (model name, status, device, batch size, role chip)
- Register New Model form (see Settings → Performance tab); Placements list; Runtime Audit Log
- Editable embedding settings (subset): `embedding.model`, `embedding.api_key` (masked), `embedding.api_base`, `embedding.dimensions_override`, `embedding.monthly_budget_usd`, `embedding.rate_limit_rpm`; audit settings: resample size, norm tolerance, drift threshold, gate_enabled + thresholds

---

## 17. SUPPORTING / OPERATIONS PAGES

- **Behavioral Hubs** (`/behavioral-hubs`): hub table (Name inline-edit, Member count, Auto-link toggle, Detection method, Updated, Open/Delete); detail (edit name, toggle auto-linking, member list 25/page); run stats (Last run, Trigger Compute, Trigger Detect, settings snapshot)
- **Diagnostics** (`/diagnostics`): tabs Services · Conflicts · Features · Error Log · Glitchtip Integration · Combined Errors · Auto Issues · Pyroscope Dashboard · Weights Diagnostics · NDCG Smoke Test · Runtime Context; filters by node, refresh, sort by status; error tools (expand+diff, filter, acknowledge, build AI prompt, copy fingerprint)
- **Scheduled Updates** (`/scheduled-updates`): tabs Alerts · Running · Schedule · History
- **Monthly Reports** (`/monthly-reports` / `/reports/monthly`): Month selector, Run Now (monthly-top-50), rendered markdown, Refresh
- **Error Log** (`/error-log`): tabs Internal Errors · Glitchtip · All Errors · Auto Issues · Pyroscope; filters (type, status, date); actions (Acknowledge, details, build AI prompt, external dashboard); Resync from Glitchtip, Flush all
- **Operations Feed** (`/operations-feed`): severity chips (All · Info · Warning · Error · Success), free-text search, Pause/Resume, Auto-follow; event rows (timestamp, severity, plain English, type+source, occurrence counter); max 500 rows
- **AI Agents / MCP** (`/mcp`): MCP health (status, %, last synced, polled 5s); agent rows (Claude Code, Codex, Antigravity — connected/disconnected, last activity); Tools Catalogue (get_top_candidates, get_dashboard_metrics, get_suggestion_status, search_suggestions, approve_suggestion, reject_suggestion, +20 more); Sentient Schedules table; Run Now (Monthly Top-50), Refresh
- **Work Queue** (`/work-queue`): Celery queue overview (queue, task count, workers, rate limit; polled 15s); task breakdown (Pending · Active · Retry)
- **Observability** (`/observability`): live service cards (name, status, storage %, Open Dashboard → Grafana; polled 15s)
- **Find Bugs** (`/find-bugs`): Refresh; Run Now · Import Latest · Prune Artifacts · Sync Context · Generate Report; filters (Search, Severity all/critical/high/medium/low, Status open/picked/fixing/resolved/deferred); findings table (Pattern · Severity · Status · File · Confirmed by · Actions: Re-evaluate · Confirm Real Bug · Create Fix Task · Assign to Agent · Run Duplicate Check); D3 severity chart
- **Performance** (`/performance`): benchmark results for Rust and Python hot paths
- **Alerts** (`/alerts`): operator alert center
- **Undo History** (`/audit/undo-timeline`): filters (Subject type, Actor, Lookback days 1–90 default 30); timeline table (Action badge create/update/delete/restore, Subject type+ID, Actor, Message, Created, Is restorable, reason); expandable old/new diff; Restore + confirm dialog
- **Preferences** (`/preferences`): appearance, language, accessibility, onboarding aggregator

---

## 18. CROSS-CUTTING PATTERNS

- **Pagination**: 25/page default (some 50); mat-paginator (index + size)
- **Status badge types**: pending/approved/applied/rejected · open/ignored/fixed · healthy/warning/error/down · completed/running/failed/queued
- **Date formats**: short (MMM d), medium, full
- **Real-time**: WebSocket for jobs; polling for health/observability/MCP (5–30s)
- **Charts**: line, bar, pie, doughnut, scatter (12+ types)
- **Tooltips**: Material tooltips with plain-English help throughout
- **Traffic filter** (global telemetry): China, Singapore excluded from GA4/Matomo/GSC imports

---

### Files not found / not present
No referenced file was reported missing across the six audits. Embedding providers are limited to exactly **two** (OpenAI, Gemini) — no local/HuggingFace/Cohere/Voyage provider exists in production code.