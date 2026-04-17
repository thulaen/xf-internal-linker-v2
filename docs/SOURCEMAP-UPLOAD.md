# Phase OB / Gap 138 — Source-map upload to the error tracker

The Sentry / GlitchTip SDK in `frontend/src/main.ts` reports stack
traces using the minified JS symbol names. Without matching source
maps the reports are unreadable. This gap wires source-map uploads
into CI.

## Why not `--hidden-source-map`?

`--source-map --hidden-source-map` keeps maps off the public asset
host but still generates them locally. That's what we want:

1. CI builds produce `*.js.map` files alongside `*.js`.
2. We upload the maps to the error tracker, not to the CDN.
3. CI then deletes the maps so the production bundle doesn't ship them.

## Build command

```bash
ng build --configuration=production \
  --source-map=true \
  --hidden-source-map=true
```

Angular 20 honours both flags via `angular.json` configurations. This
project already has `sourceMap: true` in the development config; add a
production override in `angular.json`:

```jsonc
"configurations": {
  "production": {
    // ... existing options
    "sourceMap": {
      "scripts": true,
      "styles": false,
      "hidden": true,
      "vendor": true
    }
  }
}
```

## GitHub Actions snippet

```yaml
- name: Build frontend
  run: |
    cd frontend
    npm ci
    npm run build:prod

- name: Upload source maps to GlitchTip
  if: ${{ env.GLITCHTIP_AUTH_TOKEN != '' }}
  run: |
    cd frontend/dist/xf-internal-linker-frontend/browser
    # sentry-cli is compatible with GlitchTip's Sentry-protocol ingest.
    npx @sentry/cli releases new "${GITHUB_SHA}" \
      --url "$GLITCHTIP_URL" --auth-token "$GLITCHTIP_AUTH_TOKEN"
    npx @sentry/cli releases files "${GITHUB_SHA}" upload-sourcemaps . \
      --url "$GLITCHTIP_URL" --auth-token "$GLITCHTIP_AUTH_TOKEN" \
      --url-prefix '~/'
    npx @sentry/cli releases finalize "${GITHUB_SHA}" \
      --url "$GLITCHTIP_URL" --auth-token "$GLITCHTIP_AUTH_TOKEN"

- name: Strip source maps before deploy
  run: |
    cd frontend/dist/xf-internal-linker-frontend/browser
    find . -type f -name "*.js.map" -delete
```

Env vars required for this job:
- `GLITCHTIP_URL` — e.g. `https://glitchtip.example.com`
- `GLITCHTIP_AUTH_TOKEN` — Internal Integration token with
  `project:releases` scope

## Matching the release

The SDK init in `frontend/src/main.ts` must set the same release
identifier so the backend can pair maps to traces:

```ts
Sentry.init({
  dsn: environment.glitchtipDsn,
  release: environment.buildSha,
  // ...
});
```

Set `buildSha` at build time via:

```ts
// environment.production.ts
export const environment = {
  // ...
  buildSha: '${GITHUB_SHA}',
};
```

(The placeholder is string-replaced at build time via
`file-replacements` in `angular.json` or a small `envsubst` step in
CI.)

## Local dev

Source-map upload is CI-only. Local dev continues to use
inline source maps via `ng build --configuration=development`.

## Verification

After a deploy:
1. Trigger a client-side exception from the error-log test harness.
2. Open the GlitchTip issue page.
3. Expand the stack frame — symbol names must match the original
   TypeScript file paths (e.g. `dashboard.component.ts:156`).

If frames still show minified names, the release sha on the SDK
init doesn't match the sha the CI job used — a very common
mismatch. Print both values at build time to diagnose.
