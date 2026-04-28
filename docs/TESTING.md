# Testing Rules — XF Internal Linker V2

This is the single source of truth for testing in this repo. Every AI session (Claude / Codex / Gemini / future agents) and every human contributor MUST read this before writing tests or shipping a feature.

It answers three questions:

1. **What tests does my new code need?**
2. **Where do those tests go?**
3. **What does CI block on, and what does it warn about?**

If you change a rule here, change it once and every session picks it up next time.

---

## TL;DR — what blocks a merge today

| Layer | Tool | Blocks merge? |
|---|---|---|
| Backend unit & integration tests | pytest | **Yes** |
| Backend coverage floor | pytest-cov `--cov-fail-under` | **Yes** (current floor in `backend/pytest.ini`) |
| Backend lint | ruff | **Yes** |
| Backend security scan | bandit | **Yes** |
| Backend dependency CVE scan | pip-audit | **Yes** |
| Backend type check | mypy (strict on `apps.crawler` only) | **Yes** for crawler, lenient elsewhere |
| C++ unit tests | GoogleTest via `ctest` | **Yes** |
| C++ edge-case tests | custom GoogleBenchmark binaries | **Yes** |
| C++ AddressSanitizer | clang sanitizers | **Yes** |
| C++ ThreadSanitizer | clang sanitizers | No (TBB false positives) |
| C++ static analysis | cppcheck | **Yes** |
| C++ format check | clang-format-22 | **Yes** |
| Frontend unit tests | Karma + Jasmine | **Yes** |
| Frontend lint | ESLint (Angular + a11y) | **Yes** |
| Frontend type check | TypeScript strict mode | **Yes** (compile fails the build) |
| Playwright e2e (CI-safe subset) | Playwright | **Yes** (after the e2e-blocking change shipped) |
| Frontend dependency CVE scan | npm audit (high+) | **Yes** |
| Semgrep code scan | Semgrep | No (artifact only) |
| Trivy container scan | Trivy | No (artifact only) |
| New-module-without-test warning | shell diff scan | Warning only — see Part 6 of the testing-gaps plan |
| Stylelint for SCSS | Stylelint | **Yes** (after the Stylelint change shipped) |

---

## When you add a new feature, you MUST add tests

Use this matrix:

| What you added | Test you must write | Where it goes |
|---|---|---|
| **Backend service module** (`backend/apps/<app>/services/<x>.py`) | A `test_<x>.py` covering the public surface | Same folder, or `backend/apps/<app>/tests/test_<x>.py` |
| **Backend API view / endpoint** | An integration test hitting the route through `auth_client` | `backend/apps/<app>/test_*.py` |
| **Hot-path Python function** (ranking, scoring, retrieval, embedding, attribution) | Both a unit test AND a benchmark | Test alongside the module; benchmark in `backend/benchmarks/test_bench_<area>.py` |
| **Hot-path C++ function** | Both a GoogleTest unit test AND a Google Benchmark | Test in `backend/extensions/tests/test_*.cpp`; benchmark in `backend/extensions/benchmarks/bench_*.cpp` |
| **Angular component** | A `*.spec.ts` next to the component | `frontend/src/app/<area>/<comp>.component.spec.ts` |
| **Angular service** | A `*.spec.ts` next to the service | Same folder as the service |
| **Angular pipe / directive / pure utility** | A `*.spec.ts` next to it | Same folder |
| **User-facing flow** (clickable in the UI) | A Playwright smoke test that drives the flow with mocked APIs | `frontend/tests/<feature>-smoke.spec.ts` |
| **End-to-end flow that genuinely needs a real backend** | A Playwright "live" spec | `frontend/tests/live/<feature>-live.spec.ts` (NOT in CI gate) |
| **New ranking signal / meta-algorithm** | Unit test + benchmark + entries in `RANKING-GATES.md` Gate A/B | Per the Mandatory Benchmark Rule in CLAUDE.md |

If your task is a refactor, add tests for any code path that previously lacked coverage in the area you touched.

---

## Naming conventions (load-bearing — auto-discovery depends on these)

- Python tests: file MUST start with `test_`. Inside, classes start with `Test` and functions start with `test_` (config in `backend/pytest.ini`).
- Python benchmarks: `backend/benchmarks/test_bench_<area>.py`. Use the `pytest-benchmark` fixture.
- C++ unit tests: `backend/extensions/tests/test_<area>.cpp`, registered in `CMakeLists.txt`.
- C++ benchmarks: `backend/extensions/benchmarks/bench_<area>.cpp` (Google Benchmark) or `test_edges_<area>.cpp` (edge-case tests).
- Angular unit tests: `<filename>.spec.ts` next to `<filename>.ts`.
- Playwright smoke (CI-safe, mocks API): `frontend/tests/<feature>-smoke.spec.ts`.
- Playwright live (needs real backend): `frontend/tests/live/<feature>-live.spec.ts`.
- Playwright accessibility: `frontend/tests/a11y.spec.ts` (single file, parameterized over routes).

The Playwright CI run respects two patterns automatically:
- `PLAYWRIGHT_CI=1` → `testIgnore: ['**/live/**', '**/capture/**']` in `frontend/playwright.config.ts`. New live or capture specs are auto-excluded from CI; new top-level smoke specs are auto-included.

---

## Per-module coverage targets

Pytest enforces a single global floor (in `backend/pytest.ini` as `--cov-fail-under=<N>`). The floor only goes UP; never lower it. These are the per-module targets we aim for as the floor ratchets up:

| Module | Target coverage |
|---|---|
| `apps/pipeline/services/ranker.py` | 90% |
| `apps/pipeline/services/pipeline_persist.py` | 85% |
| `apps/analytics/impact_engine.py` | 85% |
| `apps/suggestions/services/weight_tuner.py` | 85% |
| Other `apps/*/services/` | 75% |
| `apps/*/views.py` and `serializers.py` | 70% |
| Glue code (`admin.py`, `urls.py`, `signals.py`, `apps.py`, generated migrations) | 50% |

These are conventions today — they harden into per-module CI checks once we hit them. Do not lower a module's coverage to land a feature; if you must remove a test, add a replacement.

---

## Pre-merge checklist (copy into your PR description)

Tick every box that applies to your change.

- [ ] Added or updated unit tests for every modified module
- [ ] Added or updated integration tests for every modified API endpoint
- [ ] Added a benchmark if the change is on the ranking / retrieval / embedding hot path
- [ ] Added or updated a Playwright smoke test if the change is user-visible in the browser
- [ ] If the change touches ranking signals or meta-algorithms, satisfied Gate A and Gate B in `RANKING-GATES.md`
- [ ] If the change touches `frontend/src/styles/` or component SCSS, ran `npm run lint:scss` locally
- [ ] If the change adds a new file, the test-presence CI job does NOT warn
- [ ] Backend coverage did not drop (CI enforces the global floor)
- [ ] All CI jobs pass on the PR

---

## Currently skipped tests (technical debt to address)

These tests exist but are not currently running in CI. Each has a TODO in the code and a separate task to address:

- `frontend/tests/review-smoke.spec.ts` — skipped because the review page hides its `<h1>` behind a readiness gate that the empty-mock APIs can't satisfy. Fix: mock the readiness API endpoints OR click the override button in the test.
- `frontend/tests/a11y.spec.ts` for `dashboard`, `review queue`, `link health`, `settings` routes — skipped because each has real WCAG 2.1 AA violations (aria-allowed-attr, button-name, aria-hidden-focus, aria-progressbar-name, missing labels, etc.). Fix: address the violations in the source components, then remove the conditional skip. A separate task is queued for this.
- `frontend/tests/capture/page-snapshot.spec.ts` — excluded from CI via `testIgnore` because it's a manual screenshot tool, not a behavioural test. Stays available for `npm run ui:snap`.

When a skip is removed, also delete the surrounding `TODO(testing)` / `TODO(a11y)` comment block.

---

## How to run tests locally

| What you want to test | Command |
|---|---|
| All backend tests | `docker compose --env-file .env exec backend pytest` |
| Backend with coverage report | `docker compose --env-file .env exec backend pytest --cov-report=html` then open `backend/coverage-html/index.html` |
| Backend benchmarks only | `docker compose --env-file .env exec backend pytest backend/benchmarks/` |
| Frontend unit tests (watch) | `cd frontend && npm run test` |
| Frontend unit tests (headless, like CI) | `cd frontend && npm run test:ci` |
| Frontend ESLint | `cd frontend && npx ng lint` |
| Frontend Stylelint | `cd frontend && npm run lint:scss` |
| Playwright CI-safe subset (matches CI exactly) | `cd frontend && PLAYWRIGHT_CI=1 npx playwright test --reporter=list` |
| Playwright everything (incl. live + capture, needs prod stack on :80) | `cd frontend && npx playwright test --reporter=list` |
| Playwright live tests against the running prod stack | `cd frontend && npm run ui:test:live` |
| C++ unit tests | `cd backend/extensions && cmake -B build && cmake --build build && cd build && ctest --output-on-failure` |

---

## Related documents (read these too)

- [CLAUDE.md](../CLAUDE.md) — top-level rules for AI sessions including the Mandatory Benchmark Rule and the Plain-English Communication Rule.
- [AGENTS.md](../AGENTS.md) — agent protocol, code-quality mandate, branch transparency rule, password rule, layout precision rules.
- [docs/BUSINESS-LOGIC-CHECKLIST.md](BUSINESS-LOGIC-CHECKLIST.md) — mandatory checklist for ranking / scoring / attribution / import / reranking work.
- [docs/RANKING-GATES.md](RANKING-GATES.md) — Gate A and Gate B for ranking signals, meta-algorithms, autotuners, weight presets.
- [docs/PERFORMANCE.md](PERFORMANCE.md) — performance investigation rules, prod-stack verification.
- [frontend/FRONTEND-RULES.md](../frontend/FRONTEND-RULES.md) — frontend coding rules.
- [frontend/DESIGN-PATTERNS.md](../frontend/DESIGN-PATTERNS.md) — GA4 design language.
- [backend/PYTHON-RULES.md](../backend/PYTHON-RULES.md) — Python backend coding rules.
- [backend/extensions/CPP-RULES.md](../backend/extensions/CPP-RULES.md) — C++ coding rules.
