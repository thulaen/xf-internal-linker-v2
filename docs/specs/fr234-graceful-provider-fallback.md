# FR-234 — Graceful provider fallback

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Graceful provider fallback (circuit breaker) |
| **Settings prefix** | `embedding.fallback_provider`, `embedding.monthly_budget_usd` |
| **Pipeline stage** | Embed |
| **Helper** | `apps.pipeline.services.embeddings._attempt_graceful_fallback` |
| **Alert event** | `embedding.provider_fallback` (consumed by the Embeddings page and diagnostics alerts) |

## 2 · Motivation (ELI5)

API providers run out of credits. API keys get revoked. 429 rate-limits
happen. When any of this happens mid-batch, we don't want the pipeline to
crash and leave the user with half-embedded data. Instead: save the
checkpoint, switch to the fallback provider (local by default), and keep
going. The user sees one alert and the work finishes.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Nygard, 2018 — *"Release It! Design and Deploy Production-Ready Software"* (2nd ed., Pragmatic Bookshelf). Circuit-breaker pattern, ch. 5. ISBN 978-1680502398. |
| **Exponential backoff** | Lamport, Anderson 1984 — exponential-backoff in distributed systems. |
| **Industry prior art** | AWS SDK retry-with-jitter; Google Cloud client libraries retry pattern. |
| **What we reproduce** | The "open-circuit" response: isolate the failing dependency, route around it, emit an observable signal. |
| **What we diverge on** | We don't implement half-open probes because our fallback is local (always available) — we simply re-enter the hot loop with the new provider. Operator re-enables the API provider manually via the Embeddings page. |

## 4 · Triggers (what counts as a failure?)

From `apps.pipeline.services.embedding_providers.errors`:

| Exception | Reason code | Action |
|---|---|---|
| `BudgetExceededError` | `budget` | Fallback immediately |
| `AuthenticationError` | `auth` | Fallback immediately |
| `RateLimitError` | `rate_limit` | Fallback after provider's own retries exhaust |
| `TransientProviderError` | `transient` | Fallback after provider's own retries exhaust |
| Other `ProviderError` | various | Re-raise (no fallback) |

Provider-internal retries (tenacity-style exponential backoff up to 5 attempts) happen first. Fallback kicks in only if those exhaust.

## 5 · Output contract

- `_attempt_graceful_fallback` returns the new provider instance on success, or `None` on failure (caller re-raises the original error).
- `AppSetting("embedding.provider")` is atomically updated to the fallback value.
- Provider cache (`embedding_providers.clear_cache()`) is purged so subsequent batches resolve to the new provider.
- `emit_operator_alert(event_type="embedding.provider_fallback", severity="warning", payload={failing_provider, fallback_provider, reason_code, reason_message})` is fired.
- The failing batch is retried once with the new provider; on double failure the error surfaces.

## 6 · Resume semantics

- Mid-job checkpoint (`SyncJob.checkpoint_last_item_id`) persists before the swap.
- Resume uses the filter `embedding IS NULL`, **not** signature match. Items already embedded with the old provider stay (no re-spend, no data loss).
- `EmbeddingCostLedger` has `unique_together=[job_id, provider]` → the same job under the new provider writes a **new** row, not a duplicate.
- Fortnightly audit (FR-231) later detects the mixed-signature state and can re-unify if the operator wants.

## 7 · Hyperparameters

| Setting key | Type | Default | Source of default |
|---|---|---|---|
| `embedding.fallback_provider` | str | `"local"` | Project policy — local is always available |
| `embedding.monthly_budget_usd` | float | 50.0 | Internal budget envelope |
| `embedding.max_retries` | int | 5 | AWS SDK exponential-backoff convention |
| `embedding.timeout_seconds` | int | 30 | HTTP default |

## 8 · Test plan

1. **Unit** — monkey-patch the provider's HTTP client to raise `AuthenticationError`; call `_encode_batch_via_provider` with `job_id="X"`; verify the fallback activates and the second call returns vectors from the local provider.
2. **Alert** — confirm `emit_operator_alert` fires with `event_type="embedding.provider_fallback"` once.
3. **No-loop guard** — set `embedding.fallback_provider` equal to the failing provider; confirm the function returns `None` and the original error re-raises.
4. **Cost ledger** — after a fallback, confirm two rows in `EmbeddingCostLedger` for the same `job_id` (one per provider), cost not double-counted.
