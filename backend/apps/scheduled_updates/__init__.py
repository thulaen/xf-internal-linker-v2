"""Scheduled Updates — prod-only scheduler for background refresh jobs.

Every long-running refresh (PageRank, TrustRank auto-seeder, LDA topic
refresh, KenLM retrain, Node2Vec walks, feedback-aggregator sweeps, etc.)
runs through this orchestrator instead of direct Celery beat entries.

The orchestrator enforces three hard rules:

1. **11am-11pm local window only.** The laptop wakes around 10 am and
   sleeps around 11 pm and is off overnight; any job that would start
   before 11:00 or after 23:00, or would still be running past 23:00,
   is refused at the window guard. Window widened from 13-23 → 11-23
   on 2026-04-25 to give the operator two extra hours of capacity.
2. **Strict serial execution.** A Redis lock (`scheduled_updates:runner`)
   ensures at most one job runs at a time. Per-job multicore is fine
   (joblib / multiprocessing inside a single job) but two heavy jobs
   never contend for CPU or RAM.
3. **Pause / resume / catch-up.** Jobs report progress via Django
   Channels, honour a `pause_token`, and surface missed windows as
   deduped alerts (one row per (job, calendar day, alert type)).

See `plans/check-how-many-pending-tidy-iverson.md` for the full
architecture and `docs/PERFORMANCE.md` §12 for the prod-stack rule that
shaped this design.
"""
