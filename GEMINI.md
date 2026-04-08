# Gemini Instructions

**Before suggesting new features, check `AI-CONTEXT.md` § Deduplication & Overlap Rules.**
**Before any frontend work, read `frontend/FRONTEND-RULES.md` first.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**
**Before any C++ work, read `backend/extensions/CPP-RULES.md` first.**
**Before any C# work, read `services/http-worker/CSHARP-RULES.md` first.**

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

