# FR-235 — Embeddings sidenav page

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Embeddings (sidenav page) |
| **Route** | `/embeddings` (authGuard-protected) |
| **Component** | `frontend/src/app/embeddings/embeddings.component.ts` (standalone, Angular 20) |
| **Backend viewset** | `backend/apps/api/embedding_views.py` (function-based views with `@api_view`) |
| **URLs** | `backend/apps/api/urls.py` — paths prefixed `/api/embedding/` |

## 2 · Motivation (ELI5)

Everything a reviewer needs to manage embeddings lives in one sidenav page:
what provider is active, what model, what it costs, how much budget is left,
how well each provider scores on our history, and the decision log from the
quality gate. Clicking a radio button switches providers live — no
redeploy, no shell commands, no migration. For a vibe coder, this is the
cockpit.

## 3 · Design language source of truth

| Field | Value |
|---|---|
| **GA4 reference** | `frontend/DESIGN-PATTERNS.md` (extracted 2026-04-20). Card anatomy, 4 px grid, semantic tokens, M3 Expressive states. |
| **Theme file** | `frontend/src/styles/default-theme.scss` — single source for colour/spacing tokens. |
| **Accessibility** | WCAG 2.1 AA. Uses `design:accessibility-review` skill before merge. |
| **Usability heuristics** | Nielsen's 10 — visibility of system status, user control, error recovery (surfaced via the Snackbar on every action). |
| **Angular Material** | v20. Standalone components; `@if` / `@for` control flow; signals. Never custom-roll anything Material provides. |

## 4 · Tabs

| Tab | Contents | Backend endpoint(s) |
|---|---|---|
| **Overview** | Active provider chip, model/dim/signature, hardware tier, coverage bar, spend-by-provider | `GET /api/embedding/status/` |
| **Providers** | Radio-group switch (local/openai/gemini), per-provider test-connection button, API-key form (password input + visibility toggle), config fields | `GET/POST /api/embedding/provider/`, `GET/POST /api/embedding/settings/`, `POST /api/embedding/test-connection/` |
| **Run Control** | Trigger audit / bake-off buttons, live coverage progress bar | `POST /api/embedding/audit/run/`, `POST /api/embedding/bakeoff/run/` |
| **Bake-off** | Table of `EmbeddingBakeoffResult` rows (provider, MRR, NDCG, Recall, separation, cost, p95 latency) | `GET /api/embedding/bakeoff/` |
| **Audit** | Last 100 `EmbeddingGateDecision` rows + gate/audit settings form | `GET /api/embedding/gate-decisions/`, `POST /api/embedding/settings/` |

## 5 · Hot-switch UX contract

1. User clicks a radio button in Providers tab.
2. `onProviderChange(name)` posts to `/api/embedding/provider/`.
3. Backend updates `AppSetting("embedding.provider")` and clears the provider cache.
4. Snackbar confirms: *"Active provider: openai"*.
5. Next batch inside `_encode_batch_via_provider` resolves the new provider via `get_provider()` — no job restart required.
6. In-flight job's current batch completes on the old provider; subsequent batches use the new provider. Checkpoint + `embedding IS NULL` resume filter guarantee no duplicate work.

## 6 · Security contract

- API key is `AppSetting(is_secret=True)`. The GET endpoint returns it masked (`****xxxx`). POST accepts plaintext and overwrites.
- All endpoints require `IsAuthenticated` DRF permission. Anon access returns 401.
- No key is ever written to logs. Provider error messages are truncated to 500 chars.

## 7 · Polling

- Overview tab polls `/api/embedding/status/` every 15 s. Cheap: the endpoint does one AppSetting lookup + one aggregate query on `EmbeddingCostLedger`. No PII in the response.

## 8 · Hyperparameters

None owned by the UI directly. The Providers / Audit tabs surface existing AppSettings (see FR-231 / FR-232 / FR-233 / FR-234 / FR-236 specs).

## 9 · Test plan

1. **Unit** — Angular `ng test` compiles the component and binds the template without console errors.
2. **Snapshot** — `preview_screenshot` of each tab in light + dark mode (theme toggle in the app shell).
3. **Accessibility** — run `design:accessibility-review` skill against `/embeddings`; must pass WCAG 2.1 AA.
4. **Design critique** — run `design:design-critique` skill; must pass the 11 anti-patterns from `frontend/DESIGN-PATTERNS.md`.
5. **End-to-end** — configure OpenAI key → test connection shows green → flip radio to OpenAI → Overview updates within 15 s poll → trigger bake-off → result appears in table.
