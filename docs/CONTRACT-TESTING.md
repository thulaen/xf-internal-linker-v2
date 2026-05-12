# Contract Testing (Pact)

Phase 5 of the test-hardening plan. Pact lets the Angular frontend declare the shape of every API call it makes, then verifies the Django backend can satisfy each declared contract. When the backend response shape drifts, the build fails before merge — the gap is caught at PR time, not at runtime.

## Scope

| Side | Stack | Where the contract lives | First contract |
|---|---|---|---|
| Consumer | Angular | `frontend/src/app/**/*.pact.spec.ts` | (scaffolding only; first contract pending) |
| Provider | Django | `backend/apps/api/tests/test_pact_provider.py` | (scaffolding only; first contract pending) |
| Broker | `pactfoundation/pact-broker` Docker service | `docker-compose.yml`, dev profile | (scaffolding only — service definition lands in a follow-up) |

C++ and Go are out of scope: C++ extensions are in-process (no HTTP contract); Go has no code in this repo yet. Placeholder `services/go/contracts/` is a Phase 8 scaffold for the future.

## Why "consumer-driven contracts"

The frontend says "I'm going to call `POST /api/foo` with `{a, b}` and I expect back `{c, d}`." Pact saves that as a JSON contract file (`frontend/pacts/<consumer>-<provider>.json`). On the backend, a provider-verification test reads that JSON and replays each interaction against the real Django view — if the view returns `{c, d, e}` (extra field — OK) or `{c}` (missing field — FAIL) or `{c, d}` with wrong types (FAIL), the test fails.

Compared to OpenAPI: Pact verifies the actual running code, not just a hand-edited spec file that can drift from reality.

## Running locally

### Consumer side (Angular)

```bash
cd frontend
npm install
# Each Pact spec is also a regular Jasmine spec; karma picks them up.
npm run test:ci -- --include='**/*.pact.spec.ts'
# Pact JSON drops into frontend/pacts/
ls pacts/
```

### Provider side (Django)

```bash
cd backend
pytest apps/api/tests/test_pact_provider.py -p randomly -q --no-cov
```

The provider verification reads `frontend/pacts/*.json` and replays each interaction against a real Django test client. Any shape mismatch is a non-zero exit.

### Broker (optional, only for cross-team verification)

```bash
docker compose --profile dev up pact-broker
# Broker UI at http://localhost:9292
```

The broker is the central registry that frontend pushes new contracts to and backend pulls them from. Useful when contracts need to roundtrip via PR review or when multiple consumers depend on one provider. Not required for in-repo verification (the JSON files are committed).

## Plain-English summary

The Angular code says "I'll send this and expect this back." Pact writes that down. The Django code is then forced to prove it actually behaves that way. If somebody changes a JSON field name on either side without updating both, the build fails before merge.

## Status: foundation only

Phase 5 lands:
- npm dep `@pact-foundation/pact` (frontend)
- pip dep `pact-python` (backend)
- This document
- Forthcoming: starter pact spec + provider test + CI jobs (tracked alongside the AutoIssue ratchet)

The first concrete contract should land alongside a backend endpoint that's about to change — that's when the value is highest.
