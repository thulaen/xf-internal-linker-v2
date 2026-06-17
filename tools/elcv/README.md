# ELCV — Effective Logical Code Volume + quality gate

A small, dependency-free toolkit that (1) **measures** how much real, unique, working logic
the code contains, and (2) **hard-blocks** code-quality violations. Pure standard library —
runs anywhere, no Docker needed to test.

```
ELCV = (LEU x SCW) + USO
```
- **LEU** — Logical Execution Units: real decision points. Comments/whitespace = 0.
- **USO** — Unique Semantic Operations: units deduplicated by a normalized-AST hash (copy-paste collapses to one; distinct calls stay distinct).
- **SCW** — Structural Complexity Weight `[0.5, 1.0]`: over-complex code is discounted, never rewarded.

Vendored / generated / build / cache / **test** code is excluded by path (ADR-006).

## Multi-scope — never hardcode a target
Targets live in **`elcv-scopes.json`** (the single source of truth). There is a **global
ceiling of 2,000,000,000 ELCV** plus named initiative scopes, each measured over its own
paths with its own target — so initiatives never clash:
- **ranklab → 28,000,000** · **aegis → 5,000,000** · **repo → 2,000,000,000** (umbrella)

USO de-duplication runs across the **whole** codebase, so two scopes can never duplicate
each other's logic — zero overlap/conflict/bloat is *enforced*, not assumed. **To add or
change an initiative, edit `elcv-scopes.json` only — do NOT hardcode a target in code or a
spec** (that's the clash that this design removes). ELCV is *measured*, not "pending on
runtime data" (ARW was removed, ADR-006).

## Files
| File | What |
|---|---|
| `elcv.py` | Python ELCV computor (AST-accurate) + CLI |
| `gate.py` | the hard-block quality gate (~26 rules) + CLI |
| `multilang.py` | Rust + TypeScript counters — **true-AST via tree-sitter** when installed, keyword fallback otherwise |
| `ts_backend.py` | the tree-sitter Rust/TS AST counter (optional dep: `requirements.txt`) |
| `exporters.py` | **multi-scope** JSON / Prometheus / board output (feeds Grafana + the app card) |
| `elcv-scopes.json` | **single source of truth for targets** (global 2B + ranklab 28M + aegis 5M); never hardcode a target |
| `grafana-elcv-dashboard.json` | importable Grafana dashboard (elcv_total / by-area / 28M gauge) |
| `test_*.py` | 43 unit tests (pure `unittest`) |

## Use it
```bash
python tools/elcv/elcv.py backend/apps --top 20      # measure + biggest files
python tools/elcv/gate.py backend/apps/pipeline       # hard gate (exit 1 on violations)
python tools/elcv/exporters.py --format board          # multi-scope meter (reads elcv-scopes.json)
python tools/elcv/exporters.py --format prometheus     # metrics for Grafana / VictoriaMetrics
python tools/elcv/exporters.py --cache tools/elcv      # cached JSON + markdown (for the app card)
python tools/elcv/multilang.py rust                    # Rust/TS counter (tree-sitter or heuristic)
```

## Test it
```bash
python tools/elcv/test_elcv.py
python tools/elcv/test_gate.py
python tools/elcv/test_multilang.py
```

## Hard-blocking gate — the rules
27 AST/line rules: long-function, oversized-file (>1200), high-complexity, high-cognitive,
deep-nesting, too-many-params, boolean-trap, too-many-returns, too-many-locals, god-class,
wildcard-import, mutable-default, silent-except, dead-code, unbounded-loop, dangerous-exec,
placeholder-stub, nested-ternary, train-wreck, mutable-global, n-plus-one, orphan-todo,
blanket-suppression, hardcoded-secret, sql-injection, cross-module-private-import,
**cross-file-duplicate** (a new function that duplicates existing logic, via the USO index).

Deferred (covered elsewhere / need a baseline): unused-imports (ruff F401/F841),
ELCV-inflation-without-new-USO and full cross-file copy-paste (release-level diff checks).

**Inline escape** (never `--no-verify`): `# elcv: allow <RULE_ID> -- <reason>` on the line.

## CI — where it hard-blocks (active)
- **Local pre-commit:** wired into `scripts/precommit-docker.sh` as
  `run_hard_gate check-elcv-gate ...`. Hard-blocks NEW violations in staged Python files.
- **Pull requests:** `.github/workflows/elcv-gate.yml` fails the PR on new violations and
  runs the tool's own tests.
- **Baseline / ratchet:** `gate-baseline.json` grandfathers all pre-existing violations, so
  the gate blocks only NEW issues — never legacy code you merely touched. The hook also
  **fails open** on an internal tool error (a bug in the gate can never brick a commit).
- **Cross-file copy-paste:** `uso-index.json` lets the gate flag a new function duplicating
  existing logic elsewhere (rule ELCV031).
- Regenerate after a big cleanup:
  `python tools/elcv/gate.py backend tools scripts --write-uso-index tools/elcv/uso-index.json`
  then `... --uso-index tools/elcv/uso-index.json --write-baseline tools/elcv/gate-baseline.json`.

## Caveats — resolved
- **Gate is active & safe** (pre-commit + PR CI; baseline-grandfathered; fail-open).
- **Cross-file copy-paste** — solved via the USO index (ELCV031).
- **Prometheus/Grafana** — the exporter + `k8s/observability/elcv-metrics-cronjob.yaml`
  publish the metrics on a schedule; one vmagent line points it at the file to go fully live.
- **Dropped rule** — the redundant "mega-function-by-ELCV" stays dropped; long-function +
  complexity already cover it (a test proved SCW makes it unable to fire).

## True-AST Rust/TS — wired (tree-sitter)
`ts_backend.py` computes real per-function LEU / USO / SCW for Rust + TypeScript via
tree-sitter (the same ELCV model as Python). It's an **optional dependency**
(`pip install -r tools/elcv/requirements.txt`) installed in CI / the quality container;
the host stays pure-stdlib and **falls back** to the keyword counter automatically. The
report shows which backend produced the number (`tree-sitter` vs `heuristic`). The gate's
27 hard-block rules are Python-AST and need no dependency.

## Honestly still follow-up (needs the live stack — not doable offline here)
- **Flipping the Grafana graph on** — needs the running vmagent pointed at the metrics file.
- **unused-imports / dead-vars** stay delegated to ruff (F401/F841); not reimplemented.
