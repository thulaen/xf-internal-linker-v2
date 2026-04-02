# Agent Instructions

All AI agents working in this repository must follow these communication rules:

- Talk to the user in plain English.
- Explain things like the user is five.
- Start with the simple version first.
- Use short sentences, concrete examples, and everyday words.
- Avoid jargon unless it is necessary. If you must use jargon, explain it immediately in simple language.
- Do not create git branches unless the user explicitly asks for a branch. Work on the main repo branch in place by default.

### UI / Theming Rule
- **No New Themes**: Never create a new CSS/SCSS theme file.
- **Default Theme Only**: All styling must use or extend `frontend/src/styles/default-theme.scss`. This rule applies to ALL AI models (Antigravity, Claude, Codex, etc.) without exception.

If another instruction is more technical, keep the meaning accurate but still explain it in the simplest plain-English way possible.

For UI checks, browser tests, and screenshots, see `docs/ui-testing.md`.
