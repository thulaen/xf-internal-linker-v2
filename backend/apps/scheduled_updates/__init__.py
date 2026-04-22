"""Scheduled Updates — prod-only scheduler for background refresh jobs.

Every long-running refresh (PageRank, TrustRank auto-seeder, LDA topic
refresh, KenLM retrain, Node2Vec walks, feedback-aggregator sweeps, etc.)
runs through this orchestrator instead of direct Celery beat entries.

The orchestrator enforces three hard rules:

1. **1pm-11pm local window only.** The laptop goes to sleep around 11 pm
   and is off overnight; any job that would start after 23:00 or would
   still be running past 23:00 is refused at the window guard.
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
