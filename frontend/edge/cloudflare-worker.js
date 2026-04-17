/**
 * Phase F1 / Gap 84 — Cloudflare Worker for static-asset edge caching.
 *
 * Intent:
 *   - Serve Angular build artifacts (main.js, polyfills.js, *.css, fonts,
 *     icons) from the CDN edge with a long-lived cache TTL. These files
 *     are immutable — their names include a content hash.
 *   - Bypass the cache for /api/* and /ws/* because those are personalised
 *     or live.
 *   - Stale-While-Revalidate for /index.html and /manifest.webmanifest so
 *     a deploy doesn't require every user to refetch at once.
 *
 * Deployment:
 *   1. wrangler init (if not already)
 *   2. wrangler deploy
 *   3. Route: https://linker.example.com/*  → this worker
 *
 * This file lives in the frontend tree (not `backend/`) because it's
 * a frontend concern — nothing in here touches Django.
 */

const STATIC_EXT = /\.(?:js|css|woff2?|ttf|otf|svg|png|jpg|jpeg|webp|ico|map)$/i;

addEventListener('fetch', (event) => {
  event.respondWith(handle(event.request, event));
});

async function handle(request, event) {
  const url = new URL(request.url);

  // Never cache API or WebSocket traffic.
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/ws/') ||
    url.pathname.startsWith('/admin/')
  ) {
    return fetch(request);
  }

  // Immutable hashed assets — cache aggressively at the edge.
  if (STATIC_EXT.test(url.pathname)) {
    const cache = caches.default;
    const cached = await cache.match(request);
    if (cached) return cached;
    const upstream = await fetch(request);
    if (upstream.ok) {
      const clone = upstream.clone();
      const headers = new Headers(clone.headers);
      headers.set('Cache-Control', 'public, max-age=31536000, immutable');
      const cachedResponse = new Response(clone.body, {
        status: clone.status,
        statusText: clone.statusText,
        headers,
      });
      event.waitUntil(cache.put(request, cachedResponse.clone()));
      return cachedResponse;
    }
    return upstream;
  }

  // HTML / manifest — stale-while-revalidate so deploys don't stampede.
  if (
    url.pathname === '/' ||
    url.pathname.endsWith('.html') ||
    url.pathname.endsWith('.webmanifest')
  ) {
    const cache = caches.default;
    const cached = await cache.match(request);
    const freshFetch = fetch(request).then((upstream) => {
      if (upstream.ok) {
        const clone = upstream.clone();
        event.waitUntil(cache.put(request, clone));
      }
      return upstream;
    });
    return cached ?? freshFetch;
  }

  // Everything else — straight pass-through.
  return fetch(request);
}
