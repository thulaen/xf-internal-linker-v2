# i18n Rollout — Plain-English Plan

## What's done (this session)

The framework is now in place. The application can be translated.

1. **Dependency added** — `@angular/localize` is in `package.json`. Run `docker compose build frontend` (or `npm install` locally) so the new package lands in the container.
2. **Polyfill registered** — `src/main.ts` imports `@angular/localize/init` before bootstrap. This makes the global `$localize` template tag available.
3. **angular.json configured** — added `"i18n": { "sourceLocale": "en-US" }` and a new `extract-i18n` builder target. Run `npm run ng -- extract-i18n` to extract every `i18n` attribute into `src/locale/messages.xlf`.
4. **First string tagged** — the "Skip to main content" link in `app.component.html` carries `i18n="@@app.skipToContent"`. This is the proof-of-life test.

## What's still hardcoded (and needs tagging)

Every component template under `frontend/src/app/` contains user-facing English strings. The pre-flight `grep i18n= --include=*.html src/` count was zero before this session and is now one. The remaining work is mechanical: walk every template, wrap user-visible text in `i18n` attributes, and move complex sentences into `$localize\`...\`` template tags inside the TypeScript.

### Target priority order

1. **Shell** — `app.component.html`, `notification-center.component.html`, `breadcrumbs.component.html`, every dialog under `shared/ui/`. ~250 strings.
2. **Login + auth flows** — `login/login.component.html`, password-reset dialogs. ~30 strings.
3. **Top 5 pages by traffic** — Dashboard, Review, Link Health, Jobs, Settings. ~600 strings (Settings alone is dense).
4. **Long-tail pages** — every other route. ~800 strings.
5. **Toast / snackbar copy in services** — error.interceptor, auth.interceptor, anywhere `MatSnackBar.open()` is called. ~80 strings.
6. **`mat-tooltip` and `aria-label` attributes** — these need the `i18n-matTooltip` / `i18n-aria-label` syntax. ~500 strings.

Total estimate: ~2,200 user-visible strings spread across 200+ template files. At a 30-strings-per-hour sweep rate, that's a ~75-hour mechanical pass.

## How to extract translations once tagging is done

```bash
npm run ng -- extract-i18n
# Produces frontend/src/locale/messages.xlf
```

For each target locale, copy `messages.xlf` to `messages.<locale>.xlf` (e.g. `messages.fr.xlf`), translate the `<target>` blocks, then build a localised bundle with:

```bash
npm run ng -- build --localize
```

Add the locale list under `i18n.locales` in `angular.json` so the CLI knows where each translated XLF lives.

## Why this matters (plain English)

Every word in the user interface is currently English. Customers in Germany, Japan, France, or anywhere else read English buttons and English error messages. We just made it possible to translate the app — but the translation work itself is a separate multi-week task. This document is the checklist for that work.
