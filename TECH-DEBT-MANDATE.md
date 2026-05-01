# TECH-DEBT-MANDATE.md — Every Session Must Refactor

**Status:** PARAMOUNT and STRICT SESSION GATE. Applies to Claude / Codex / Antigravity / Gemini / every future agent.

## The Rule

Every session must produce a measurable tech-debt reduction. If your task is "add feature X", you ALSO clean up the debt you encounter while implementing X — duplicated code, magic numbers, silent excepts, dead code, stale comments, long files, hardcoded paths, untracked TODOs, forbidden patterns.

**Per-session minimum:** 5 debt items resolved (counted from the categories below).
**Aggregate target:** reduce overall codebase debt by 80 % across the next 8-12 sessions.

This is a session gate, not a guideline. A session that ships features without any debt reduction is a protocol violation equivalent to skipping the AGENT-HANDOFF entry.

## Debt Categories (Your Sweep Targets)

| # | Category | Symptom | Fix pattern |
|---|---|---|---|
| 1 | **Duplicated boilerplate** | Same N-line block in 3+ files (e.g. `AppSetting.objects.filter(key=k).first(); row.value if row else default`) | Extract to a single helper; refactor every call site in the same PR (or schedule batched refactors) |
| 2 | **Magic numbers** | Bare numeric literal in expression with no named constant | Hoist to module-level constant with citation; the constant gets a docstring |
| 3 | **Silent exceptions** | `except Exception: pass` or `except Exception: logger.warning(...)` with no `ingest_error` | Wrap with `apps.audit.error_ingest.ingest_error()` so it's visible on `/error-log` |
| 4 | **Dead code** | Function defined but never imported anywhere | Delete (verified by `grep -r "from .* import <name>"`) |
| 5 | **Stale comments** | Comment that no longer matches the code | Rewrite or delete in the same edit (Pre-finish comment check from AGENTS.md) |
| 6 | **Long files** | `>1500` lines in a single Python file | Split into focused submodules in same package |
| 7 | **Duplicate test patterns** | Same setup boilerplate in 3+ test files | Extract to a `conftest.py` fixture |
| 8 | **Hardcoded paths** | `/app/` or `C:\` in code outside config files | Use `pathlib.Path(__file__).parent` or `settings.*` |
| 9 | **TODO without owner/deadline** | Bare `# TODO` with no link to spec/issue | Either resolve, or link to a `RPT-XXX` ticket |
| 10 | **Forbidden patterns** | `while True` without break, `.objects.all()` without slice, triple-nested for-loops, magic numbers in services | Refactor or document with explicit citation per [`PERFORMANCE-SAFE-DEFAULTS.md`](PERFORMANCE-SAFE-DEFAULTS.md) |

## Session-End Gate (mandatory)

Every `AGENT-HANDOFF.md` entry MUST include a "Tech-debt delta" line at the bottom. Format:

```
Tech-debt delta: -N debt items, -M lines refactored.
  Boilerplate extracted: <list of helpers>
  Files split: <list>
  Magic numbers hoisted: <list>
  Silent excepts wrapped: <list>
  Dead code removed: <list>
  TODOs resolved: <list>
```

A session with no "Tech-debt delta" line fails the handoff protocol. The next agent reads this line first to know what cleanup is in flight.

## Pre-Commit Gate (CI extension)

The existing `.githooks/check-no-duplicates-invariant.py` will be extended (in a future Phase 4.0a session) to scan for the seven highest-impact forbidden patterns:

1. New `except Exception:` block with no `ingest_error` call.
2. New numeric literal `> 1` and `< 1.0` outside of `__init__` arguments and constants.
3. New `while True:` without an explicit break-condition or timeout.
4. New `.objects.all()` followed by `for x in` (unbounded iteration).
5. New file with no `# (c)` or module docstring.
6. New `# TODO` without `RPT-XXX` reference.
7. New function over 50 lines (encourages splitting).

Override per-instance with `# noqa: tech-debt # justification: <reason>`.

## How To Sweep In Practice

When you open any file to add or modify code, ALSO scan it for:

1. **In the function you're touching** — fix every debt item in that function. Cheap; you're already loading it into context.
2. **In the file you're touching** — fix the highest-impact debt item (1 per file, max 3 per PR).
3. **In adjacent functions called by the function you're touching** — note the debt; if it's small, fix it; if it's large, file `RPT-XXX`.

Resist the urge to refactor the whole repo in one PR. The mandate is steady cumulative pressure, not a debt-bankruptcy push.

## Exemptions

Generated code (`*_pb2.py`, frontend `schema.d.ts`, migration files): **exempt** from refactor — they're regenerated.
Vendored third-party code under `vendor/`: **exempt**.
Test fixtures with intentional bad patterns (testing the linter itself): **exempt** if commented `# tech-debt-test-fixture`.

## Why This Rule Exists

Tech debt is the silent killer of velocity. A codebase with 30+ broad excepts in one file (verified in `embeddings.py`) makes every future change risky because the agent can't predict which paths will silently fall back. A codebase with 40+ AppSetting boilerplate sites means every settings change requires touching 40 places. A codebase with 2400-line `tasks.py` means new tasks land in the wrong file because the file is too unwieldy to split on the spot.

The mandate makes debt reduction the agent's responsibility, not the operator's. The operator is a vibe coder; they cannot audit the code. The agents must police themselves.
