## THINK-BEFORE-YOU-CODE.md — Paramount Design Discipline

**Status:** PARAMOUNT and STRICT. Applies to every agent (Claude / Codex / Antigravity / Gemini / GPT / future). Read before writing a single line.

This is the *upstream* rule that prevents the messes the other paramount files clean up after.

* [`TECH-DEBT-MANDATE.md`](TECH-DEBT-MANDATE.md) measures debt reduction *after the fact*.
* [`PERFORMANCE-SAFE-DEFAULTS.md`](PERFORMANCE-SAFE-DEFAULTS.md) blocks the worst patterns *at commit time*.
* [`NO-DUPLICATES.md`](NO-DUPLICATES.md) governs *storage*.
* **THIS rule** governs *the act of writing code itself* — what you do BEFORE you start typing, so the other rules have less to catch.

A session that produced spaghetti code, a 200-line monster handler, or three near-duplicate helpers fails this rule even if every other rule passes.

---

## The Five Pre-Write Questions (mandatory)

Before writing any new function, class, view, or service, answer these five questions in your head (or briefly in your response):

1. **DRY: Does this already exist?** Search the codebase first. If a helper already exists, use it. If a near-duplicate exists, refactor BOTH call sites to use a shared one in the same change.
2. **KISS: What is the simplest thing that works?** If you find yourself reaching for a metaclass, a deep inheritance hierarchy, or a generic factory before any concrete need, you've over-designed. Write the concrete code; abstract on the second use, not the first.
3. **Scaling: What happens at 10× and 100×?** What if there are 100K rows / 100 candidates / 100 concurrent operators? If your design breaks, redesign now, not later.
4. **Extensibility: Where is the seam for the next feature?** Single-responsibility, dependency-injected, importable in isolation. If a future feature would force you to edit a 500-line file across 10 places, you're building spaghetti.
5. **Testing: How will I prove this works without spinning up Docker?** Pure functions and small classes are testable in isolation. If your design needs a full request lifecycle to test the simplest invariant, split it.

If you can't answer all five quickly, **stop and re-design** before typing.

---

## Hard Rules (machine-checkable; pre-commit hook enforces)

| # | Rule | Limit | Override |
|---|---|---|---|
| 1 | **Function length** | ≤ 50 lines (excluding docstring + blank lines) | Split into helpers — that's the actual fix. `# noqa: long-function # justification: <reason>` ONLY for declarative dict-literal data tables that can't be sensibly split. |
| 2 | **File length** | ≤ 1500 lines | Split into focused submodules in same package. |
| 3 | **Component depth** | Frontend: ≤ 200 lines per component file, ≤ 7 props | See `frontend/FRONTEND-RULES.md`. |
| 4 | **Cyclomatic complexity** | ≤ 10 per function | Extract conditional blocks into named helpers. |
| 5 | **Argument count** | ≤ 7 positional + keyword-only | Group related args into a dataclass / dict. |
| 6 | **Nesting depth** | ≤ 4 levels of `if`/`for`/`with`/`try` | Early-return + extract helper. |
| 7 | **Duplicate code** | No 6+ line block appearing in 2+ places | Extract to helper in the SAME commit that introduces the second copy. |
| 8 | **Inline magic numbers** | None in services / models / view bodies | Hoist to module-level constant with docstring + citation. |
| 9 | **Silent excepts** | None — broad `except Exception:` must log OR ingest_error OR re-raise | Per `PERFORMANCE-SAFE-DEFAULTS.md`. |
| 10 | **Module docstring** | Every new `.py` file gets a one-line summary at the top | PEP-257. |

---

## Soft Rules (review-checkable; reviewer enforces)

* **Single Responsibility.** A class / function does ONE thing. If you can't summarise it in one sentence without "and", it's doing too much.
* **Pure functions where possible.** If a function only transforms inputs to outputs without I/O, mark it pure (no decorator needed; just keep it testable in `SimpleTestCase`).
* **Dependency injection over module-level imports.** A function that takes its database / cache / logger as a parameter is testable; one that imports from `apps.x` mid-body is not. Use module-level imports for *types*; inject for *behaviour*.
* **Composition over inheritance.** If you find yourself writing a base class with 4 subclasses each overriding 2 methods, you probably want 4 small functions + a dispatch dict.
* **Names are documentation.** A 30-line function with a clear name (`_validate_ga4_gsc_consistency`) is self-documenting. A 30-line function called `process` is a debugging nightmare.
* **No premature abstraction.** Abstract on the SECOND use, not the first. Three near-identical functions become a single helper-with-parameter; one function with vague boilerplate stays one function.
* **Migrate-as-you-touch.** When you edit a long function or a duplicated block, refactor it in the same commit per the [`TECH-DEBT-MANDATE.md`](TECH-DEBT-MANDATE.md). Leaving the file worse than you found it is a violation.

---

## Code-Duplication Test (run mentally before every commit)

Look at every helper / class / dict-literal you wrote. For each one, ask:

1. **Does the same shape appear elsewhere in this commit?** → Extract.
2. **Does the same shape appear elsewhere in the codebase?** → Refactor both call sites in this commit OR file an `RPT-XXX` ticket.
3. **Will the next operator-tunable change require editing 5 places?** → Extract a constant or a registry.

If any answer is yes and you didn't fix it: **the commit is broken, not done.**

---

## Scalability + Extensibility Pre-Flight

For any new model / service / view / background task, declare in the docstring or commit message:

* **Storage growth.** Bounded? Linear in operator activity? See [`NO-DUPLICATES.md`](NO-DUPLICATES.md) — every per-content artefact follows the `(content_hash, signal_version)` + supersede + retention pattern.
* **Time complexity** at expected input size + at 10× and 100×.
* **Concurrency.** Is it safe to call from multiple Celery workers? Single-process? Explicit lock?
* **Failure mode.** What happens when an upstream dep is missing / DB is down / network blips? Defensive coercion + `ingest_error` + degraded-but-working response?
* **The next-feature seam.** Where does the next operator-requested tweak land? A registry entry? A spec table? A new kwarg? A new Celery task? Make sure the seam exists BEFORE you ship the first version.

---

## What "Spaghetti Code" Looks Like (Forbidden)

* A view handler doing 6 ORM queries + 4 conditional rendering branches + an external API call inline.
* A service function that imports its dependencies inside the function body so you can't unit-test it without mocking 5 modules.
* A 200-line `if/elif/else` chain that should have been a registry/dispatch dict.
* A class with 12 methods where 11 of them are short and 1 is 200 lines doing the actual work.
* Three near-duplicate functions with names like `process_v1`, `process_v2`, `process_new` because the operator added a tweak instead of refactoring.
* A "config" dict that's actually flow control hidden in data (`if config["mode"] == "extra-special-case-9": …`).

---

## Pre-Commit Enforcement

The existing `.githooks/check-forbidden-patterns.py` enforces the machine-checkable subset:

* **Long function** (rule #1): warning at >50 lines.
* **Silent except** (rule #9): blocking violation.
* **Missing module docstring** (rule #10): warning.
* **Missing `@HelperConstraint` on Celery tasks** (extensibility seam): warning.

The full strict mode runs weekly via `.github/workflows/strict-debt-audit.yml`. Diff-aware mode runs per-commit.

---

## Session-End Self-Check (mandatory)

Before declaring a session done, scan everything you wrote:

* [ ] Every new function under 50 lines? (Or explicitly noqa'd with a one-line justification.)
* [ ] No new silent excepts?
* [ ] No new duplicated 6+ line blocks?
* [ ] No new inline magic numbers in services?
* [ ] Every new module starts with a one-line docstring?
* [ ] Every new Celery task has `@HelperConstraint`?
* [ ] Every new endpoint has security scope (auth + rate limit if expensive)?
* [ ] Every new helper has at least one unit test?

If any box is unchecked: it goes into the same commit, not a follow-up.

---

## How To Sweep Existing Code As You Touch It

When editing a file:

1. If a function in the file is over 50 lines: refactor it in the same commit (extract per-domain helpers).
2. If a code-block you're touching is duplicated elsewhere: extract to a helper + refactor both sites.
3. If you see a silent except: wrap it with `ingest_error()` or `logger.warning(..., exc_info=True)`.
4. If you see an inline magic number: hoist to a module-level constant with citation.
5. If you see a stale comment: rewrite or delete in the same edit.

The rule: **leave the file in better shape than you found it**, even if your task is "add feature X" not "clean up file Y".

---

## Citations + Rationale

* **Function-length 50 lines:** McConnell, *Code Complete* 2nd ed (2004) §7.4 — "Functions longer than ~50-100 lines start to lose comprehensibility."
* **Cyclomatic complexity 10:** McCabe (1976) original threshold — bug-density inflection point.
* **Single Responsibility:** Martin, *Clean Code* (2008) §3 — "A function should do ONE thing."
* **DRY:** Hunt & Thomas, *The Pragmatic Programmer* (1999) §7 — "Every piece of knowledge must have a single, unambiguous, authoritative representation."
* **KISS:** Kelly Johnson, Lockheed Skunk Works (1960) — "Keep it simple, stupid."
* **Composition over inheritance:** GoF *Design Patterns* (1994) §1 — favour object composition over class inheritance.
* **Premature abstraction:** Sandi Metz, *Practical Object-Oriented Design in Ruby* (2012) §6 — "Duplication is far cheaper than the wrong abstraction."

These aren't opinions. They are the standard professional discipline. The agent that ignores them is shipping technical debt every commit.
