"""Phase OF — Operations Feed.

Ambient narration of what the app is currently doing, deduped, in plain
English. Distinct from `apps.notifications` (urgent operator alerts)
and `apps.audit.ErrorLog` (stack traces for debugging) — this layer is
the running commentary a vibe-coder can leave open to watch the system
work.
"""

default_app_config = "apps.ops_feed.apps.OpsFeedConfig"
