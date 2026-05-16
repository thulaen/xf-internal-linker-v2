# Module: platform

**Layer:** 1 (foundation).
**Status:** Stub — full detail lands in slice 3.
**Maps to today:** parts of `backend/apps/audit/`, `backend/apps/pipeline/services/hardware_profile.py`, `backend/apps/pipeline/services/disk_pressure.py`, error-tracking glue, feature-flag helpers.

## Plain-English summary

The platform module is the toolbox every other module reaches into. It owns the things that are not about content, not about ranking, and not about external sources — but everything else needs them. Settings, hardware profile, disk-pressure circuit breaker, error tracking, feature flags, plain-English helpers, audit logging.

If you can describe the function without naming "post", "thread", "rank", "source", "user-facing surface", or "queue", it probably belongs in platform.

## Public interface

`platform.api` exports the small set of helpers that every other module is allowed to call. Examples slated for slice 3:

- `HardwareProfile` and `get_hardware_profile()`
- `require_free_disk(path: Path, min_bytes: int)`
- `feature_flag(name: str) -> bool`
- `audit_log(actor: str, action: str, payload: dict)`
- `track_error(exc: Exception, *, context: dict)`
- `peHelper(text: str)` — the plain-English helper string normaliser

The full list lands in slice 3 alongside the move. Anything not in `api.py` stays private.

## Job (the "and"-test)

Platform owns one job: **provide cross-cutting helpers that have no business knowledge.** If the helper needs to know what a post or a link is, it belongs in a higher module.

## Owned tables

- `AuditLog` (audit trail)
- `OperatorAlert` (operator-facing warnings)
- `FeatureFlag` (feature gating)

The full list arrives with the slice-3 move.

## Dependencies

Platform imports from **no other module**. It is the deepest layer. Other modules import from it.

## Open questions

- Where does the GlitchTip / error-tracking glue live — `platform` or `operations`? Slice 3 has to pick. Current lean: a thin wrapper in `platform.api`, the dashboards in `operations`.
- Should `peHelper` belong in `governance` (since it is part of the plain-English rule) or in `platform` (since every module uses it)? Current lean: `platform`, because the rule belongs in `governance` but the helper is cross-cutting.

## Citations

- ISO/IEC/IEEE 42010:2022 — separating cross-cutting concerns from business concerns at the architecture level.
- Parnas 1972 — information hiding for utility-like modules.

## Slice that moves this module

Slice 3. Smallest and most-used module, so it moves first; the rest of the codebase gets to depend on a stable `platform.api` before its own slice arrives.
