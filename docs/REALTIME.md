# Realtime — Plain-English Recipe for Adding a Live-Updating Page

This is a four-step recipe. Every page that should update live when something
changes on the backend follows the same four steps. No magic.

Phase R0 infrastructure was shipped on 2026-04-16. The backend lives at
`backend/apps/realtime/`. The frontend lives at
`frontend/src/app/core/services/realtime.service.ts`.

---

## What "live" means here

Today, most pages fetch once when you open them. If a technician fixes Redis
at 10:01:00, a dashboard that was loaded at 10:00:55 keeps showing "Redis
broken" until you refresh. That's not caching — it's stale data sitting on
an open page.

The realtime system fixes that. Every interesting state change on the backend
gets broadcast on a **topic**. Any open tab that is subscribed to that topic
receives the update in under a second, with zero extra HTTP requests.

---

## The four steps

Say you want the **Crawler** page to update live whenever a `CrawlSession`
finishes.

### Step 1 — Pick a topic name

Pick a short, dot-separated string. Examples: `diagnostics`, `settings.runtime`,
`crawler.sessions`, `jobs.history`. The name is free-form; producers and
subscribers just need to agree.

Rule of thumb: one topic per user-facing data surface. Don't create a topic
per row — put the row id in the payload instead.

### Step 2 — Emit from the backend when the data changes

Add a Django signal in the app that owns the model. If the app doesn't have
a `signals.py` yet, create one.

```python
# backend/apps/crawler/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.realtime.services import broadcast
from .models import CrawlSession


TOPIC = "crawler.sessions"


@receiver(post_save, sender=CrawlSession)
def _on_crawl_session_saved(sender, instance, created, **kwargs):
    broadcast(
        TOPIC,
        event="entity.updated" if not created else "entity.created",
        payload={
            "id": str(instance.id),
            "state": instance.state,
            "pages_crawled": instance.pages_crawled,
        },
    )


@receiver(post_delete, sender=CrawlSession)
def _on_crawl_session_deleted(sender, instance, **kwargs):
    broadcast(TOPIC, "entity.deleted", {"id": str(instance.id)})
```

Then wire the signals in the app's `apps.py`:

```python
# backend/apps/crawler/apps.py
from django.apps import AppConfig

class CrawlerConfig(AppConfig):
    name = "apps.crawler"

    def ready(self) -> None:
        from . import signals  # noqa: F401 — import side effects register signals
```

That's it for the backend.

### Step 3 — Subscribe from the component

```ts
// frontend/src/app/crawler/crawler.component.ts
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RealtimeService } from '../core/services/realtime.service';

@Component({ /* ... */ })
export class CrawlerComponent implements OnInit {
  private realtime = inject(RealtimeService);
  private destroyRef = inject(DestroyRef);

  sessions: any[] = [];

  ngOnInit(): void {
    // One-time REST load for the page.
    this.loadSessionsFromApi();

    // Live updates for the same page. Cleanup is automatic when
    // the component is destroyed — no manual unsubscribe needed.
    this.realtime
      .subscribeTopic<{ id: string; state: string; pages_crawled: number }>('crawler.sessions')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(({ event, payload }) => {
        if (event === 'entity.deleted') {
          this.sessions = this.sessions.filter(s => s.id !== payload.id);
          return;
        }
        const idx = this.sessions.findIndex(s => s.id === payload.id);
        if (idx >= 0) {
          this.sessions[idx] = { ...this.sessions[idx], ...payload };
        } else {
          this.sessions.push(payload);
        }
      });
  }

  private loadSessionsFromApi(): void {
    /* your existing HTTP fetch */
  }
}
```

The `RealtimeService` handles:
- Opening one WebSocket per tab (lazy — only on first subscribe).
- Re-sending subscribes after a reconnect.
- Exponential-backoff reconnect (1s → 30s cap, with jitter).
- Deduplicating — five components subscribing to the same topic still
  cause only one backend subscribe frame.

### Step 4 — Verify with the two-window test

1. Open two browser windows side by side on the same page.
2. In window A, trigger the change (e.g. start a crawl).
3. Window B should update within 1 second with **no** list-endpoint request.

Check the Network tab of window B's devtools — you should see the WebSocket
frame come through, no HTTP GET.

---

## Optional: restrict a topic to staff only

Edit `backend/apps/realtime/permissions.py` and add an entry:

```python
_EXACT_RULES: dict[str, PermissionCheck] = {
    "settings.runtime": _is_staff,
    "your.staff.only.topic": _is_staff,   # add here
}
```

Non-staff subscribers will receive `{"type":"subscription.ack", "denied":["your.staff.only.topic"]}`
and stay silent.

---

## Don'ts

- **Don't** open a raw `new WebSocket(...)` for a new feature. Use
  `RealtimeService.subscribeTopic`. The raw WebSockets in `jobs.component.ts`
  and `notification.service.ts` are grandfathered — leave them alone.
- **Don't** broadcast inside a request/response cycle. Use `post_save` /
  `post_delete` signals so the broadcast survives if the HTTP request errors
  out partway through.
- **Don't** put a lot of data in the payload. If the row is heavy, broadcast
  just an id + state and let the client fetch the detail on demand.
- **Don't** create a topic per row. One topic per surface. Row id goes in
  the payload.
- **Don't** emit inside a tight loop — wrap in a single "N rows changed"
  event instead, so the Operations Feed dedup window (Phase OF) can do its
  job.

---

## Files in this system

| File | Purpose |
|---|---|
| `backend/apps/realtime/consumers.py` | The WebSocket endpoint. Handles subscribe / unsubscribe frames. |
| `backend/apps/realtime/services.py` | The `broadcast(topic, event, payload)` helper. |
| `backend/apps/realtime/permissions.py` | Topic → permission map. |
| `backend/apps/realtime/routing.py` | URL pattern `/ws/realtime/`. |
| `frontend/src/app/core/services/realtime.service.ts` | Singleton WS manager + `subscribeTopic()` API. |
| `frontend/src/app/core/services/realtime.types.ts` | Shared TS types. |

---

## Questions people keep asking

**Q: What's the difference between this and the existing Jobs / Notifications WebSockets?**
They predate this system and handle job-progress streams and operator-alert
fan-out. They still work. Do not migrate them. Anything new goes through
`/ws/realtime/`.

**Q: What happens if the WebSocket is down?**
The service auto-reconnects with exponential backoff. When it recovers, it
re-sends subscribes for every topic the tab still cares about. Subscribers
never see the gap, only the reconnect delay. Consumers that need to show a
"reconnecting" UI hint can watch `RealtimeService.connectionStatus$`.

**Q: What happens if the client subscribes before the socket opens?**
The subscribe frame is sent when the socket opens. No messages are lost as
long as the server wasn't in the middle of a broadcast for that exact topic
during the connecting window — which is negligible in practice because the
client page is also busy rendering.

**Q: How do I write an end-to-end test?**
Use `channels.testing.WebsocketCommunicator`. Backend has an example pattern
at `backend/apps/pipeline/tests/` for the Jobs consumer; the realtime
consumer can be tested the same way.
