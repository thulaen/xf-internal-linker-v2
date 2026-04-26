# FR-097 -- Crawl Priority Scheduling via OR-Tools

## Overview

**Requested:** 2026-04-10
**Status:** Pending
**Priority:** Medium
**Research basis:** Wolf J. et al., "Optimal Re-Visiting of Web Pages", WWW 2002. Knapsack formulation for crawl scheduling under budget constraints.
**Library:** Google OR-Tools (`pip install ortools`, Apache 2.0, ~80 MB)

## Problem Definition

Simple version: Given a limited crawl budget (X pages per hour), which pages should be recrawled first to get the most value?

Technical version: The crawler has a fixed throughput budget per scheduling window. Each page has a freshness-decay cost (how stale it has become since last crawl) and a traffic-weighted value (how much user traffic it receives). The goal is to select the subset of pages that maximizes total freshness-weighted value without exceeding the crawl budget. This is a bounded knapsack problem.

## What's Wanted

- A crawl priority scheduler that replaces FIFO/sitemap ordering with value-optimized ordering.
- The scheduler runs before each crawl session and outputs a prioritized URL list.
- Pages with high traffic and high staleness get recrawled first.
- Pages with low traffic and recent crawls get deferred.
- The budget constraint is respected (never exceed X pages per window).

## Algorithm

### Inputs
- `pages[]`: all known content items with fields: `page_id`, `url`, `last_crawl_ts`, `ga4_pageviews_30d`, `pagerank_score`, `content_hash`
- `budget`: max pages to crawl in this window (from settings)
- `current_time`: now

### Value Function
For each page:
```
staleness = (current_time - last_crawl_ts).total_hours()
traffic_value = log(1 + ga4_pageviews_30d) * pagerank_score
freshness_cost = 1 - exp(-staleness / half_life_hours)
priority_value = traffic_value * freshness_cost
```

### Optimization
OR-Tools CP-SAT solver:
```
maximize: sum(x[i] * priority_value[i] for i in pages)
subject to: sum(x[i] for i in pages) <= budget
            x[i] in {0, 1}
```

This is a 0-1 knapsack with uniform item weights (each page costs 1 crawl slot). For uniform weights, the optimal solution is simply the top-K by priority_value. CP-SAT handles the general case where pages have variable crawl costs (e.g., large pages cost 2 slots due to rate limiting).

### Output
Ordered list of page_ids to crawl, sorted by priority_value descending.

## Specific Controls / Behaviour

### Settings (stored in `core_appsetting`)
- `crawl_priority.enabled` (bool, default: `false`) -- enable value-based crawl scheduling
- `crawl_priority.budget_per_window` (int, default: `500`) -- max pages per crawl window
- `crawl_priority.half_life_hours` (float, default: `168.0`) -- freshness decay half-life (1 week)
- `crawl_priority.min_staleness_hours` (float, default: `24.0`) -- don't recrawl pages newer than this
- `crawl_priority.traffic_weight` (float, default: `0.7`) -- weight for GA4 traffic in value function
- `crawl_priority.pagerank_weight` (float, default: `0.3`) -- weight for PageRank in value function

### Integration Point
- Called by `CrawlSessionService.cs` before building the crawl frontier
- If enabled, replaces the default sitemap/FIFO ordering
- If disabled or OR-Tools not installed, falls back to existing ordering

### Fallback Behaviour
- If `ortools` is not installed: log warning, use existing FIFO ordering
- If no GA4 data available: use PageRank only (traffic_weight forced to 0)
- If no PageRank data available: use staleness only

## Implementation Notes for the AI

### Architecture alignment
- Python service in `backend/apps/crawler/services/crawl_priority.py`
- Dispatched as a Celery task and consumed by the Python worker (post-2026-04 the C# HttpWorker is decommissioned; all crawl orchestration is Celery-only)
- OR-Tools runs in Python process (`pip install ortools` in backend/requirements.txt)
- C++ is NOT used here -- OR-Tools provides its own C++ solver behind the Python API

### Files to touch
- `backend/apps/crawler/services/crawl_priority.py` (NEW) -- priority scheduler
- `backend/apps/crawler/tasks.py` -- add crawl_priority task
- `backend/requirements.txt` -- add `ortools>=9.9`
- `backend/apps/crawler/services/crawl_session.py` -- call priority scheduler before building the frontier (legacy `services/http-worker/.../CrawlSessionService.cs` was decommissioned 2026-04)
- `backend/apps/core/migrations/` -- add settings keys
- `frontend/src/app/settings/` -- add crawl priority settings card

### Regression risks
1. **Risk:** OR-Tools solver timeout on large page sets (>100K pages)
   **Mitigation:** Set solver time limit (5 seconds). For uniform-weight knapsack, the greedy solution (sort by value, take top-K) is optimal -- use greedy as fast path, CP-SAT only for variable-weight cases.

2. **Risk:** Missing GA4 or PageRank data leads to degenerate priority (all zeros)
   **Mitigation:** Fallback logic uses staleness-only ordering when traffic/PR data is unavailable.

3. **Risk:** OR-Tools package size (~80 MB) increases Docker image
   **Mitigation:** OR-Tools is a pip install, not a compiled C++ extension. It adds to the Python Docker layer only.

## Test Plan

### Unit tests
1. Priority value calculation: verify staleness decay formula
2. Greedy solver: top-K selection matches expected ordering
3. CP-SAT solver: optimal solution for small known-answer instance
4. Fallback: correct behaviour when OR-Tools not installed
5. Fallback: correct behaviour when GA4/PageRank data missing

### Integration tests
1. Full crawl session with priority scheduling enabled
2. Verify crawl order matches expected priority ordering
3. Budget constraint respected (never exceeds budget_per_window)

### Edge cases
- Zero pages to crawl
- Budget larger than total pages (crawl everything)
- All pages have same staleness (should rank by traffic)
- All pages have same traffic (should rank by staleness)
- Pages with last_crawl_ts = NULL (never crawled, max priority)
