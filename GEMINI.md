# Gemini Instructions

**Before any frontend work, read `frontend/FRONTEND-RULES.md` first.**

Repository communication rule:

- Talk to the user in plain English.
- Explain things like the user is five.
- Keep answers simple, direct, and practical.
- Use examples instead of jargon when possible.
- **Strict Theme Rule**: Do not create new themes and **forbid local overrides**. `default-theme.scss` is the only theme allowed. Use global utility classes for all structural changes. This applies to all AI models.
- **Material Design 3**: This app uses M3. Do not revert to M2 APIs. Do not override M3 visual defaults.
- **Spacing Rule**: Nothing may touch an edge. Always use spacing tokens from `_theme-vars.scss`. Never hardcode pixel values in a component.
- **Design Uniformity**: Every screen uses the same inputs (`mat-form-field outline`), same buttons (`mat-flat-button` / `mat-stroked-button`), same errors (`mat-error`), same cards (`mat-card`). No one-off styles.
