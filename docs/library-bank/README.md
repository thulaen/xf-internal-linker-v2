# Library Expansion Bank — generated index + boot brief

This folder is the **machine-readable index layer** of the Library Expansion Bank
(Paper Trail "Sticky 2"). Do **not** hand-edit the JSON files here — they are
generated from the database by `manage.py library_bank_export_index`.

## Layers

1. **Ledger (human source of truth):**
   [`docs/specs/fr-approved-library-expansion-bank.md`](../specs/fr-approved-library-expansion-bank.md)
   — the full ~37k-word curated document (256 libraries, 14 capability recipes,
   60 implementation slices, anti-pattern bank, future-reuse protocol). Files have
   no word limit, so this is the "bottomless" part.
2. **Index (this folder, generated):**
   - `AGENT-BOOT-BRIEF.md` — the ~30-line note registered as Paper Trail Sticky 2.
     Read this at session start, **not** the full ledger.
   - `library-bank.index.json` — every library card (slug, capability, status, owner).
   - `capability-recipes.json` — the 14 "if you need X, use Y" recipes.
   - `accepted-capabilities.json` — only `accepted` libraries, grouped by capability.
   - `library-status-ledger.json` — slug → promotion status + benchmark proof.
3. **Database (enforcement):** the `library_registry` Django app holds one row per
   card + one row per recipe. The commit gates read these rows.

## How agents use it

- Need a capability? `manage.py library_bank_lookup "<capability or keyword>"`.
- Found something better that isn't here? `manage.py library_bank_add ...` to file it
  as a **candidate** (never blocks a commit). Benchmark + `library_bank_promote` to
  make it the official **accepted** default.
- A speed test failed the 20× gate? Search the bank first, then search online and
  file the finding with `library_bank_add --found-during-perf-exemption`.

See the spec for the full acceptance gates and anti-patterns.
