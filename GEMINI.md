# Gemini Instructions

**PARAMOUNT — Plain-English Communication Rule (all agents — Gemini / Antigravity / Claude / Codex / every future agent):** Read [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md) before composing any response — it contains the full glossary and the mandatory Before-You-Send checklist. Every response, commit message, error report, status update, and user-facing surface MUST be written in plain English the user can understand. The user is a vibe coder — they use AI exclusively and don't write code. Three required parts:
1. **What I'm doing / will do** — describe the action in everyday words. Define every technical term the moment it's used. No unexplained acronyms (FR-XXX, ISS-XXX, RPT-XXX, MMR, BGE-M3, FAISS, RSQVA, etc.) — use the plain-English substitutes from the glossary in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md).
2. **What was accomplished** — at the end of every change, state in plain English what now works that didn't before, plus which files changed and why.
3. **What has issues or errors** — surface failures honestly. If something broke, say what broke, why, and what you'll do about it. Never bury errors in jargon. Never silently move on after a failure. Never claim success when something is partial. If a step was skipped, say so.
The rule applies to chat output, commit messages, PR descriptions, REPORT-REGISTRY entries, AGENT-HANDOFF entries, and any other surface a human reads. Skipping any of the three required parts is a protocol violation. Silence on errors is forbidden.
**Before sending any response, run the Before-You-Send checklist in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md). If any of the four checklist questions is NO, rewrite the response before sending.**

**PARAMOUNT — THINK BEFORE YOU CODE (the upstream rule):** STOP and answer the 5 pre-write questions BEFORE typing any new function/class/view/service. (1) DRY — search the codebase first; reuse or refactor BOTH sites if a near-duplicate exists. (2) KISS — write the simplest thing that works; no premature abstraction. (3) Scaling — declare what happens at 10× and 100× input. (4) Extensibility — declare WHERE the next feature lands BEFORE shipping the first version. (5) Testability — pure functions + small classes that test in `SimpleTestCase` without Docker. Hard limits: ≤50 lines per function, ≤1500 per file, ≤10 cyclomatic complexity, ≤7 args, ≤4 nesting levels, no duplicated 6+ line blocks. **Leave every file in BETTER shape than you found it.** Read [`THINK-BEFORE-YOU-CODE.md`](THINK-BEFORE-YOU-CODE.md) before writing a single line — this is the upstream rule that prevents the messes the other paramount files clean up after.

**Before suggesting new features, check `AI-CONTEXT.md` § Deduplication & Overlap Rules.**
**Before any frontend work, read `frontend/FRONTEND-RULES.md` first.**
**Before any frontend work, also read `frontend/DESIGN-PATTERNS.md` — the authoritative GA4 design language reference (extracted 2026-04-20). Card anatomy, co-location rules, button sizing, spacing tokens, and the 11 anti-patterns that contaminate layouts.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**
**Before any C++ work, read `backend/extensions/CPP-RULES.md` first.**
**Before writing any code, follow the Code Quality Mandate in `AGENTS.md` — it applies to every task.**

**For backend sessions, follow the canonical migration and safe-prune policy in `AGENTS.md`.**
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
