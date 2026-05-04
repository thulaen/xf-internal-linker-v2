# Gemini Instructions

**PARAMOUNT — THINK BEFORE YOU CODE (the upstream rule):** STOP and answer the 5 pre-write questions BEFORE typing any new function/class/view/service. (1) DRY — search the codebase first; reuse or refactor BOTH sites if a near-duplicate exists. (2) KISS — write the simplest thing that works; no premature abstraction. (3) Scaling — declare what happens at 10× and 100× input. (4) Extensibility — declare WHERE the next feature lands BEFORE shipping the first version. (5) Testability — pure functions + small classes that test in `SimpleTestCase` without Docker. Hard limits: ≤50 lines per function, ≤1500 per file, ≤10 cyclomatic complexity, ≤7 args, ≤4 nesting levels, no duplicated 6+ line blocks. **Leave every file in BETTER shape than you found it.** Read [`THINK-BEFORE-YOU-CODE.md`](THINK-BEFORE-YOU-CODE.md) before writing a single line — this is the upstream rule that prevents the messes the other paramount files clean up after.

**Before suggesting new features, check `AI-CONTEXT.md` § Deduplication & Overlap Rules.**
**Before any frontend work, read `frontend/FRONTEND-RULES.md` first.**
**Before any frontend work, also read `frontend/DESIGN-PATTERNS.md` — the authoritative GA4 design language reference (extracted 2026-04-20). Card anatomy, co-location rules, button sizing, spacing tokens, and the 11 anti-patterns that contaminate layouts.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**
**Before any C++ work, read `backend/extensions/CPP-RULES.md` first.**
**Before writing any code, follow the Code Quality Mandate in `AGENTS.md` — it applies to every task.**

**For backend sessions, follow the canonical migration and safe-prune policy in `AGENTS.md`.**

Repository communication rule:

- Talk to the user in plain English.
- Explain things like the user is five.
- Keep answers simple, direct, and practical.
- Use examples instead of jargon when possible.
- **Strict Theme Rule**: Do not create new themes and **forbid local overrides**. `default-theme.scss` is the only theme allowed. Use global utility classes for all structural changes. This applies to all AI models.
- **Material Design 3 Expressive**: This app uses M3 Expressive. Do not revert to M2 APIs. **Fully embrace** pronounced hover states, spring-motion transitions, and expressive focus rings — do NOT suppress or flatten them.
- **Spacing Rule**: Nothing may touch an edge. Always use spacing tokens from `_theme-vars.scss`. Never hardcode pixel values in a component.
- **Design Uniformity**: Every screen uses the same inputs (`mat-form-field outline`), same buttons (`mat-flat-button` / `mat-stroked-button`), same errors (`mat-error`), same cards (`mat-card`). No one-off styles.

## Layout Precision Rules (all four are mandatory)

See `AGENTS.md` "Layout Precision Rules" for the full detail. Apply these every time:

- **Rule A** — Filter chips: first chip must have `16px` left clearance. Never flush against a container wall.
- **Rule B** — Form fields: `24px` card padding, always. Sparse forms centred horizontally and vertically.
- **Rule C** — Buttons: `16px` clearance from all edges. Baseline-align buttons with adjacent form fields.
- **Rule D** — Compound labels: use ` • `, ` — `, or `: ` between two metadata strings. Never bare whitespace.
