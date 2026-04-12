# Native Runtime Policy

This file defines the repo policy for C++ and Python runtime work.

Use this file for:
- native C++ extensions
- Python fallback paths
- diagnostics and operator-visible runtime issues
- future feature requests that add hot loops or heavy runtime lanes

## Simple Rule

- C++ is the default speed path for hot ranking and pipeline loops.
- Python is the safety net and behavior reference path for both orchestration and business logic.
- No runtime path is trusted unless it is visible in diagnostics and covered by tests.

## Do Not Duplicate Existing Systems

This repo already has runtime-health and issue surfaces.

Reuse these instead of inventing a second dashboard:
- `backend/apps/diagnostics/models.py`
- `backend/apps/diagnostics/health.py`
- `backend/apps/diagnostics/views.py`
- `frontend/src/app/diagnostics/`

Important existing signals:
- `native_scoring` already exists as a service snapshot.
- `scheduler_lane`, `runtime_lanes`, and `embedding_specialist` already exist as service snapshots (all owned by Celery/Python).
- `SystemConflict` already exists for duplication, drift, and mismatch reporting.
- `ErrorLog` already exists for operator-visible failures.

If a new runtime issue needs UI visibility, extend the existing diagnostics system. Do not create a separate native-only issue center unless a human explicitly asks for one.

## Runtime Defaults

### C++

Use C++ by default for:
- ranking hot loops
- reranking hot loops
- candidate retrieval hot loops
- batch math kernels
- repeated graph steps
- tokenization or parsing that runs at scale

Do not add a Python-only hot loop for a ranking-affecting feature unless a human explicitly approves the slower path.

### Python

Python must exist for:
- correctness reference behavior
- safe fallback when native code is missing, unsafe, or disabled
- parity checks during rollout
- simpler debugging of product behavior

Python is not the preferred speed path for hot loops.



## Required Guardrails For Every New C++ Path

Every new or changed C++ implementation must have all of the following:

1. A named Python twin
- The Python path must match behavior closely enough to act as the truth source.

2. A gate
- Use a clear `HAS_CPP_EXT`-style runtime gate.
- The code must fail safely to Python when the native path is unavailable.

3. Parity tests
- Compare C++ output to the Python reference.
- Cover normal inputs, empty inputs, malformed inputs, edge values, and large inputs.

4. FR-level acceptance coverage
- At least one test must prove the feature still behaves correctly at the product level, not just at the helper-function level.

5. Input validation
- Validate array shapes, dtypes, bounds, null/empty cases, and unsupported values before entering dangerous logic.

6. Memory-safety checks
- Native changes should be verified with sanitizer builds when supported.
- Minimum target: AddressSanitizer and UndefinedBehaviorSanitizer on Linux CI or equivalent local verification.

7. Benchmark proof
- Native code must show either a real speedup or a clear scalability benefit.
- If there is no meaningful speedup, prefer the simpler implementation unless a human approves the complexity.

8. Fallback proof
- Show that the feature still works when the compiled module is missing.

9. Plain-English diagnostics
- Operators must be able to tell whether the C++ path is active, skipped, degraded, or falling back.

## Memory And Safety Rules For C++

- Prefer simple ownership and RAII.
- Prefer `std::vector`, `std::string`, smart pointers, and scoped objects over manual lifetime management.
- Avoid raw owning pointers unless there is a strong measured reason.
- Check indexes and lengths before access.
- Treat all Python/NumPy input as untrusted until validated.
- Keep Python object interaction small and explicit.
- Release the GIL only when the code path is proven safe to run without touching Python objects.
- Do not trade memory safety for micro-optimizations unless benchmark evidence is strong and review is explicit.

## Bug-Checking Rules

Every native change should be checked at four levels:

1. Unit behavior
- Does the function return the right answer?

2. Parity behavior
- Does C++ match Python?

3. Product behavior
- Does the user-visible feature still work?

4. Runtime safety
- Does it stay safe under stress, malformed input, and larger data?

Recommended extra checks:
- fuzz tests for tokenizers, parsers, and text-processing code
- benchmark tests for hot loops
- memory and crash checks in CI

## GUI Issue Visibility Policy

Runtime issues for C++ and Python must be visible on the operator-facing diagnostics UI.

The dedicated place is the existing System Health / Diagnostics surface:
- route: `frontend/src/app/diagnostics/`
- backend source: `backend/apps/diagnostics/`

### What must be visible

For every important runtime lane or native speed path, show:
- active runtime owner: C++, Python fallback, Celery, or unknown
- current state: healthy, degraded, failed, disabled, or not installed
- short plain-English explanation
- next action step
- metadata that answers "is the speed path active and helping?"

### Minimum metadata for native paths

When relevant, include:
- `runtime_path`: `cpp`, `python`, or mixed
- `fallback_active`: true or false
- `fallback_reason`
- `compiled`: true or false
- `importable`: true or false
- `safe_to_use`: true or false
- `last_benchmark_ms` or benchmark summary
- `speedup_vs_python`
- `unsupported_input_count` if relevant
- `last_error_summary`

### Where to put issues

- Use `ServiceStatusSnapshot` for current runtime/service health.
- Use `ErrorLog` for concrete failures and stack traces.
- Use `SystemConflict` for duplication, drift, spec/code mismatch, or conflicting runtime states.

Do not hide runtime trouble only in logs.

## Review Policy For AI Agents

AI agents may help write and review native code, but they are not the final safety system.

Use agents for:
- implementation help
- edge-case review
- memory-risk review
- parity-test suggestions
- FR/code mismatch review

Do not rely on agents alone for:
- memory safety
- correctness claims
- speed claims
- release approval

The final judge is:
- automated tests
- parity checks
- sanitizer runs
- benchmarks
- operator-visible diagnostics

## Required Questions For Any Native PR

Every PR that adds or changes native code should answer:
- What hot path is this accelerating?
- Where is the Python twin?
- What proves C++ matches Python?
- What proves fallback still works?
- What proves this is actually faster?
- What diagnostics show the active runtime path?
- What happens on empty, malformed, and large inputs?

## Repo-Specific Notes

- This policy does not replace `AI-CONTEXT.md`. It consolidates the native-runtime rules into one stable place.
- Existing repo direction already supports this policy:
  - C++ default for ranking hot loops
  - Python fallback as safety net
  - visible diagnostics for speed-path status
- Future work should extend the current diagnostics system rather than creating a duplicate native-runtime dashboard.
