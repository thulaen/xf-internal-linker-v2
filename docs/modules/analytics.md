# Module: analytics

**Layer:** 2 (business).
**Status:** Stub — full detail lands in slice 8 (lands alongside `graph`).
**Maps to today:** Google Search Console connectors, Google Analytics 4 connectors, Matomo connector, the impact-tracking tables, the rate-limited paid-API caller.

## Plain-English summary

The analytics module owns the read-only data taps to external measurement systems. Google Search Console, Google Analytics 4, Matomo. It owns the ingest cadence, the rate limiter, the per-source dedupe (no two ingests of the same `(date, source, dimension)` row), and the impact-tracking tables that the pipeline reads as signals.

If a function pulls a number from GSC, GA4, or Matomo, it belongs here.

## Public interface

`analytics.api` exports the typed signal records that `pipeline` consumes. Examples slated for slice 8:

- `SearchQuery`, `PageImpression`, `Conversion`
- `ImpactWindow` (the time slice the score uses)
- `iter_recent_impressions(content_id: int, since: datetime) -> Iterable[PageImpression]`
- `record_applied_link_impact(suggestion_id: int, window: ImpactWindow) -> Impact`

GSC, GA4, and Matomo client classes are private. Only the typed records and the verbs cross the boundary.

## Job (the "and"-test)

Analytics owns one job: **read-only ingestion from external measurement systems plus the impact-tracking math that depends on them.** It does not own the XenForo or WordPress connectors (`sources`) or the ranking that consumes its signals (`pipeline` consumes through `analytics.api`).

## Owned tables

- `GscIngestCursor`, `Ga4IngestCursor`, `MatomoIngestCursor`
- `SearchQuery`, `PageImpression`, `Conversion`
- `AppliedLinkImpact`
- The per-source rate-limit state owned by `platform.api`'s rate limiter, but seeded with analytics-specific bucket sizes

The full list arrives with the slice-8 move.

## Dependencies

- `platform` (rate limiter, paid-API guard, disk-pressure circuit breaker)
- `content` (resolve content IDs to URLs to pages)

Analytics does **not** depend on `pipeline`, `suggestions`, `graph`, `operations`, `governance`. It is a sibling of `pipeline`, `suggestions`, and `graph` at Layer 2.

## Open questions

- Matomo for goldmidi.com tracks Site 2 (WordPress) and Site 3 (XenForo `/community/`). Confirm the per-site rate-limit and token-rotation cadence (180 days) live in `analytics`, not in `sources` or `platform`.
- The XenForo native "Statistics" field is an analytics signal, not a content source — slice 8 confirms the boundary.

## Citations

- Joachims 2007 TOIS — *Evaluating Retrieval Performance Using Clickthrough Data.* (Position-bias-corrected click-through used in impact tracking.)
- RFC 6585 — rate-limit response handling used by all three connectors.

## Slice that moves this module

Slice 8 (with `graph`). Lands after `pipeline` and `suggestions` because both consume `analytics.api`.
