# ADR 0002 — Public interface lives in a single `api.py` per module

**Date:** 2026-05-16
**Status:** Accepted
**Deciders:** Project owner.
**Related:** ADR 0001.

## Context

Once the backend is split into modules (ADR 0001), each module needs a clear public surface. Three conventions are common in Python:

1. **`__init__.py` barrel** — list every exported name in the package's `__init__.py`.
2. **Explicit `api.py`** — a separate file at the module root that re-exports the public names.
3. **No declared public surface** — let consumers import whatever they find.

Option 3 is what we have today and is what the modular-monolith style is meant to fix. Of the two declared-surface options, the trade-off is between brevity (option 1) and clarity (option 2).

The `__init__.py` barrel is shorter to write but mixes Django's app-loading mechanics with the public-surface declaration. Django runs `__init__.py` at app load and the file already imports models, signals, and config. Adding the public-surface declaration to the same file makes it harder to read and easier to break with circular-import bugs.

The explicit `api.py` is one extra file per module but separates two concerns cleanly: `__init__.py` handles Django's app loading, `api.py` handles the public surface.

## Decision

Every module declares its public surface in **one file**: `api.py`, at the module root.

```text
backend/apps/<module>/
├── __init__.py     # Django app config; not the public surface
├── api.py          # the public surface — re-exports from private files
├── models.py       # private
├── services/       # private
└── ...
```

Rules:

1. `api.py` contains only re-exports. It does no real work.
2. `api.py` declares `__all__` listing every public name.
3. Every public function and class has a type signature.
4. Cross-module imports use `from apps.<module>.api import X`.
5. Reaching into private files (anything not in `api.py`) is forbidden and is blocked by `import-linter` from slice 2 onward.

## Consequences

**Positive:**

- The public surface is one greppable file per module. A reader can answer "what does `pipeline` expose?" in 10 seconds.
- `__init__.py` keeps its Django role; the public surface change does not interfere with Django's app registry.
- `import-linter` rules read clearly: "no import from `apps.X` may target anything except `apps.X.api`."
- Typed signatures on `api.py` give the type checker the most leverage.

**Negative:**

- One extra file per module.
- Renaming a private function still requires updating `api.py` if it was re-exported.

**Trade-offs accepted:**

- The `api.py` file may grow large for a module with many exports. The plan accepts this: if `api.py` grows beyond ~30 names, the module is probably doing two jobs and should be split.

## References

- ADR 0001 — adopting the modular-monolith style.
- Percival & Gregory 2020 — *Architecture Patterns with Python*, chapter on bounded contexts and public interfaces.
- import-linter — tool that enforces this rule, see <https://import-linter.readthedocs.io/>.
- Nx enforce-module-boundaries — same pattern in the TypeScript world, see <https://nx.dev/concepts/decisions/project-dependency-rules>.
