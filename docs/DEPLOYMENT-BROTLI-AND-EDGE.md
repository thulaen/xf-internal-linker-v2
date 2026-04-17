# Phase F1 / Gaps 83 + 84 — Brotli compression + Cloudflare edge cache

Two deployment-layer concerns that aren't application code: Brotli
compression of static assets, and a Cloudflare Worker that does edge
caching for the same assets.

## Gap 83 — Brotli

Django's built-in `django.middleware.gzip.GZipMiddleware` only serves
gzip. Brotli typically compresses Angular bundles 15-25% smaller and
is supported by every current browser.

### Option A — Nginx (recommended for this project)

Add this to the production nginx config that fronts Daphne:

```nginx
# Requires the nginx-module-brotli package (or a build with
# --with-http_brotli_static_module).
brotli on;
brotli_comp_level 6;
brotli_static on;            # serve foo.js.br when the file exists
brotli_types
    text/plain
    text/css
    text/javascript
    application/javascript
    application/json
    application/xml
    image/svg+xml
    font/ttf
    font/otf;
```

Build artefacts must be pre-compressed into `.br` files so nginx can
`brotli_static on` them. Add this to the frontend production build
pipeline (CI, not dev):

```bash
cd frontend/dist/xf-internal-linker-frontend/browser
find . -type f \( -name "*.js" -o -name "*.css" -o -name "*.html" \) \
  -exec brotli --best --keep {} \;
```

### Option B — Django middleware

If the deployment has no nginx in front (rare for this project),
install `django-compression-middleware`:

```bash
pip install django-compression-middleware==0.5.0
```

Add to `backend/config/settings/base.py` above `GZipMiddleware`:

```python
MIDDLEWARE = [
    "compression_middleware.middleware.CompressionMiddleware",
    # ... rest unchanged
]
```

### Verification

```bash
curl -H "Accept-Encoding: br" -I https://your-host/main.js | grep -i content-encoding
# Expected: Content-Encoding: br
```

## Gap 84 — Cloudflare Worker edge cache

Script lives in `frontend/edge/cloudflare-worker.js`.

### Deployment

```bash
cd frontend
npx wrangler init --yes
# edit wrangler.toml to point main = "edge/cloudflare-worker.js"
npx wrangler deploy
```

Then in the Cloudflare dashboard, add a route:

```
Pattern: linker.example.com/*
Worker:  xfil-edge-cache
```

### What the worker does

- `/api/*`, `/ws/*`, `/admin/*` → pass-through, zero caching.
- Hashed static assets (`*.js`, `*.css`, `*.woff2`, images, `*.map`) →
  cached at the edge with `public, max-age=31536000, immutable`.
- `/`, `*.html`, `*.webmanifest` → stale-while-revalidate: serve the
  cached copy immediately, revalidate in the background.

### Verification

```bash
curl -I https://linker.example.com/main-abc123.js \
  | grep -i cf-cache-status
# First hit: MISS
# Second hit: HIT
```
