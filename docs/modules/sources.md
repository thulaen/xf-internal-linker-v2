# Module: sources

**Layer:** 1 (foundation).
**Status:** Stub — full detail lands in slice 5.
**Maps to today:** `backend/apps/xenforo/`, `backend/apps/wordpress/`, webhook receivers, SSH-export fallbacks, rate-limited API clients.

## Plain-English summary

The sources module is the only place that reaches outside the local app to read content. It owns the read-only connectors to XenForo (REST API, webhooks, SSH-export fallback) and to WordPress (REST API). Sources hands fresh content to `content`. Sources never writes back to the live forum or blog.

If a function makes a network call to XenForo or WordPress, it belongs here.

## Public interface

`sources.api` exports the small set of connector entry points. Examples slated for slice 5:

- `XenForoClient`, `WordPressClient`
- `sync_xenforo_posts(since: datetime) -> int`
- `sync_wordpress_pages(since: datetime) -> int`
- `WebhookEvent` (typed record for incoming XenForo / WordPress webhooks)
- `dispatch_webhook(event: WebhookEvent)`

The full list lands in slice 5. Rate-limit configuration is a private detail; only the call surface is public.

## Job (the "and"-test)

Sources owns one job: **read-only external content connectors.** If the function writes back to the source, it is forbidden. If the function ingests Google Search Console or Google Analytics 4 data, that is `analytics`, not `sources`.

## Owned tables

- `SyncJob`, `SyncCursor` (state for incremental syncs)
- `WebhookEvent` (incoming webhook audit trail)
- `RateLimitBucket` (per-host token-bucket state for `platform.api`'s rate limiter)

The full list arrives with the slice-5 move.

## Dependencies

- `platform` (rate-limiter, disk-pressure circuit breaker, error tracking, feature flags)

Sources does **not** depend on `content` directly. The content rows it produces are written through `content.api`. The slice-5 plan covers exactly how that boundary is drawn.

## Open questions

- Should the WordPress connector live in this module or in a plugin (per `docs/v2-master-plan.md` § 13)? Current lean: in this module today, with the plugin system slated as a slice-10 follow-up.
- The XenForo native "Statistics" field for Site 3 (`/community/`) feeds analytics, not source content — confirm the boundary so the field's ingest is in `analytics`, not in `sources`.

## Citations

- Parnas 1972 — connectors as boundary modules.
- RFC 6585 (rate-limit response codes) — the rate-limiter behaviour is shaped by these.

## Slice that moves this module

Slice 5. Sibling of `content` at Layer 1; can move after `content` because `content` is the upstream consumer of `sources`'s output.
