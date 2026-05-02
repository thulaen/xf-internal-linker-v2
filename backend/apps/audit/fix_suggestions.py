"""
Plain-English fix suggestions for ErrorLog entries.

Phase GT Step 4. The operator intelligence layer — each error row on the
Diagnostics page gets a human-readable "how to fix this" line below the
traceback. Rules live here in one place so the sync task + internal
ingest helper share the same lookup.

Adding a new pattern = append one tuple to _RULES.
"""

from __future__ import annotations

import re

# Each rule is (compiled regex, plain-English fix). The regex is matched
# against a concatenation of error_message, fingerprint, and step so that
# patterns like "step=spacy.load" can trigger without touching the message.
_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"CUDA.*out of memory|OOM", re.I),
        "GPU ran out of VRAM. Lower batch size in Settings → Pipeline, or "
        "restart the embeddings worker: `docker compose restart celery`.",
    ),
    (
        re.compile(r"torch\.cuda|nvidia-smi|no CUDA", re.I),
        "GPU not detected. Run `nvidia-smi` on the host; if it fails, "
        "reinstall NVIDIA drivers. The app will fall back to CPU automatically.",
    ),
    (
        re.compile(r"spacy.*not.*found|Can't find model|en_core_web_sm", re.I),
        "spaCy model is missing. Run "
        "`docker compose exec backend python -m spacy download en_core_web_sm`.",
    ),
    (
        re.compile(
            r"ConnectionError.*redis|Redis.*refused|redis.*ConnectionError", re.I
        ),
        "Redis is down. Run `docker compose restart redis`.",
    ),
    (
        re.compile(
            r"psycopg|OperationalError.*database|could not connect to server", re.I
        ),
        "Postgres is down or unreachable. Check `docker compose ps postgres` "
        "and `docker compose logs postgres --tail=50`.",
    ),
    (
        re.compile(r"faiss|index.*not.*loaded", re.I),
        "FAISS index failed to load. Trigger a rebuild from "
        "Settings → Pipeline → Rebuild embeddings.",
    ),
    (
        re.compile(r"EMBEDDING_MODEL|sentence-transformers|huggingface", re.I),
        "Embedding model failed to load. Verify HF cache: "
        "`docker compose exec backend ls /root/.cache/huggingface`.",
    ),
    (
        re.compile(r"Celery.*worker|worker lost|WorkerLostError", re.I),
        "Celery worker crashed. Restart: `docker compose restart celery`. "
        "Check logs: `docker compose logs celery --tail=200`.",
    ),
    (
        re.compile(r"disk.*full|No space left|ENOSPC", re.I),
        "Disk is full. Run `docker system prune -af && docker volume prune -f`. "
        "Use the Safe Prune card on /health for a guided cleanup.",
    ),
    (
        re.compile(r"permission denied|EACCES", re.I),
        "Filesystem permissions error. Check container user/group and the "
        "mounted volume's host-side permissions.",
    ),
]

# Phase 4.4 — Beginner-Friendly Failure Recovery (extension to 30+ rules).
# Each rule below covers a specific failure pattern observed in production
# logs over the past 3 months. The plain-English fix is deliberately
# concrete (named docker command, named settings panel) so the operator
# doesn't have to guess.
_RULES.extend([
    (
        re.compile(r"DiskPressureError|free disk.*<.*GB|projected_total.*exceed", re.I),
        "Disk pressure circuit-breaker tripped. Run "
        "`scripts/prune-verification-artifacts.ps1` to free Docker cache, "
        "then `docker_compact_vhd.ps1` to return space to Windows.",
    ),
    (
        re.compile(r"ThermalThrottleError|GPU.*temperature.*\d{2}.*°C|thermal", re.I),
        "GPU is throttling above 85 °C. Pause heavy work for ~5 minutes "
        "via the Quick-Controls panel, or improve case airflow. The job "
        "auto-resumes when the GPU cools below 75 °C.",
    ),
    (
        re.compile(r"FAISS.*single.*worker|_assert_single_worker", re.I),
        "FAISS demands one worker per process. Set "
        "`CELERY_WORKER_CONCURRENCY=1` on the embeddings worker and "
        "`docker compose restart celery-worker-pipeline`.",
    ),
    (
        re.compile(r"OPQ.*codebook.*not.*active|opq_codebook_version.*mismatch", re.I),
        "OPQ codebook is missing or stale. Trigger "
        "`pipeline.train_opq_codebook` from /settings/passage-relevance "
        "or wait for the weekly Celery beat run.",
    ),
    (
        re.compile(r"WebSocket.*4003|websocket.*token|sock.*rejected", re.I),
        "WebSocket auth failed (ISS-021). Token didn't reach the handshake. "
        "Check `frontend/src/environments/environment.ts` wsBaseUrl points "
        "via nginx (port 80) and the user is logged in.",
    ),
    (
        re.compile(r"HelperNode.*not.*found|HELPER_NODE_NAME.*not.*registered", re.I),
        "Helper PC sent a heartbeat but no HelperNode row exists for it. "
        "Enroll via POST /api/settings/helpers/ with the helper's name + "
        "one-time token.",
    ),
    (
        re.compile(r"makemigrations.*not.*detected|No changes detected", re.I),
        "A model field changed without a migration. Run "
        "`docker compose exec backend python manage.py makemigrations` "
        "and commit the new file.",
    ),
    (
        re.compile(r"port 80.*already in use|EADDRINUSE.*:80", re.I),
        "Port 80 collision. Another service (IIS / WebDeploy / Skype) is "
        "holding it. `netstat -ano | findstr :80` to find the PID; stop "
        "or reconfigure that service.",
    ),
    (
        re.compile(r"AppSetting.*does not exist|matching query does not exist.*AppSetting", re.I),
        "An AppSetting key was read before its seed migration ran. "
        "Run `manage.py migrate` and re-trigger the failing operation.",
    ),
    (
        re.compile(r"OPENAI.*api.*key|openai\.AuthenticationError|401.*openai", re.I),
        "OpenAI API key missing or invalid. Set OPENAI_API_KEY in .env "
        "and restart the backend. Check spend cap in /settings/embeddings.",
    ),
    (
        re.compile(r"GEMINI.*api.*key|google\.api_core.*Unauthenticated", re.I),
        "Gemini API key missing or invalid. Set GEMINI_API_KEY in .env "
        "and restart the backend.",
    ),
    (
        re.compile(r"GSC.*credentials|google\.auth.*GSC|search-console.*invalid_grant", re.I),
        "GSC OAuth tokens expired or revoked. Re-authorize via "
        "/settings/gsc → 'Reconnect Google account'.",
    ),
    (
        re.compile(r"GA4.*credentials|GA4.*Unauthorized|analytics\.api_core.*401", re.I),
        "GA4 service-account credentials missing. Upload the JSON key "
        "via /settings/ga4 → 'Upload service account file'.",
    ),
    (
        re.compile(r"Matomo.*token|Matomo.*401|Matomo.*invalid_token", re.I),
        "Matomo auth token invalid. Regenerate in Matomo Admin → "
        "Personal → Security → Auth tokens, paste in /settings/matomo.",
    ),
    (
        re.compile(r"WordPress.*401|WP.*Application Password.*invalid", re.I),
        "WordPress Application Password rejected. Generate a new one in "
        "WP Admin → Users → Profile → Application Passwords, then update "
        "/settings/wordpress.",
    ),
    (
        re.compile(r"XenForo.*authentication|XF.*invalid.*api_key", re.I),
        "XenForo API key invalid. Check the API key in your XenForo "
        "admin panel + the value in /settings/xenforo.",
    ),
    (
        re.compile(r"FK_.*violates|foreign key constraint.*violation", re.I),
        "A foreign-key constraint was violated. Usually caused by a "
        "delete-cascade that didn't fire. Check the affected model's "
        "on_delete behavior and re-run the failing query.",
    ),
    (
        re.compile(r"Lock wait timeout|deadlock detected", re.I),
        "Postgres deadlock or lock timeout. Click 'Why is it slow?' on "
        "the running job — likely two heavy tasks contending. Pause "
        "non-essential workers via Quick-Controls.",
    ),
    (
        re.compile(r"OOMKilled|memory cgroup", re.I),
        "Linux killed the container for using too much RAM. Lower "
        "embedding batch size or bump the container's `mem_limit` "
        "in docker-compose.yml.",
    ),
    (
        re.compile(r"channels.*group_send|channel layer.*error", re.I),
        "Realtime broadcast failed. Redis is the channel layer; check "
        "`docker compose ps redis` and reconnect via the WebSocket.",
    ),
    (
        re.compile(r"slow query.*log|pg_stat_statements.*\d{4,} ms", re.I),
        "A Postgres query took >2 seconds. Inspect on /diagnostics → "
        "'Slow queries' tab. Likely missing index or seq-scan on a big table.",
    ),
])


_GENERIC = (
    "Open the 'Copy for AI' button on this error, paste the prompt into "
    "Claude or Codex, and let it propose a fix. Include the GlitchTip link "
    "if present."
)


# Phase 4.4 — Action chips. Each chip is rendered as a one-click button
# next to the fix-suggestion text on /error-log so the operator can act
# without copy-pasting commands. ``action_url`` is the POST endpoint;
# empty action_url = informational chip (no click handler).
def suggest_action_chips(
    error_message: str = "",
    fingerprint: str = "",
    step: str = "",
) -> list[dict[str, str]]:
    """Return zero or more action chips for the given error signature.

    Plain-English: instead of just text "Run the prune script", we hand
    the operator a button that POSTs to /api/system/disk-prune/ for
    them. Each chip declares its own endpoint + tooltip so the UI
    renders without per-error custom code.

    The mapping is keyed by the fix's regex pattern (we re-run the
    pattern match here rather than passing through the rule index).
    Returns [] when no specific action exists — UI falls back to the
    generic 'Copy for AI' button.
    """
    blob = f"{error_message}\n{fingerprint}\n{step}"

    # Each pattern → list of one or more chips. Order matters: the
    # operator's most-likely-useful action first.
    _CHIPS = [
        (
            re.compile(r"DiskPressureError|disk.*full|No space left|ENOSPC", re.I),
            [
                {
                    "label": "Free Docker disk now",
                    "action_url": "/api/system/disk-prune/",
                    "tooltip": "Runs the safe-prune script (~16 GB typical reclaim).",
                },
                {
                    "label": "View disk pressure",
                    "action_url": "/diagnostics?focus=disk-pressure",
                    "tooltip": "Open the disk-pressure card with current watermarks.",
                },
            ],
        ),
        (
            re.compile(r"CUDA.*out of memory|OOM|MemoryError", re.I),
            [
                {
                    "label": "Reclaim GPU cache",
                    "action_url": "/api/diagnostics/gpu-memory-cleanup/",
                    "tooltip": "Clears unused VRAM PyTorch is hoarding.",
                },
                {
                    "label": "Lower batch size",
                    "action_url": "/settings/passage-relevance",
                    "tooltip": "Open the embedding batch-size setting.",
                },
            ],
        ),
        (
            re.compile(r"WebSocket.*4003|websocket.*token", re.I),
            [
                {
                    "label": "Re-login",
                    "action_url": "/login",
                    "tooltip": "Refresh the auth token used in the WebSocket handshake.",
                },
            ],
        ),
        (
            re.compile(r"FAISS|index.*not.*loaded|opq_codebook", re.I),
            [
                {
                    "label": "Rebuild index",
                    "action_url": "/api/settings/passage-relevance/rebuild-index/",
                    "tooltip": "Triggers an immediate FAISS / OPQ codebook rebuild.",
                },
            ],
        ),
        (
            re.compile(r"Celery.*worker|worker lost|WorkerLostError", re.I),
            [
                {
                    "label": "Pause everything",
                    "action_url": "/api/system/master-pause/",
                    "tooltip": "Stops all background work so the failing worker can be safely restarted.",
                },
            ],
        ),
        (
            re.compile(r"ThermalThrottleError|thermal", re.I),
            [
                {
                    "label": "Wait for cooldown",
                    "action_url": "",
                    "tooltip": "GPU is above 85 °C. Job auto-resumes when it cools below 75 °C.",
                },
            ],
        ),
    ]

    for pattern, chips in _CHIPS:
        if pattern.search(blob):
            return chips
    return []


def suggest(error_message: str = "", fingerprint: str = "", step: str = "") -> str:
    """
    Return a plain-English fix suggestion for the given error signature.

    Matches against a composite of message, fingerprint, and step so a
    rule can key on any of them. Returns a generic "ask an AI" hint when
    nothing matches.
    """
    blob = f"{error_message}\n{fingerprint}\n{step}"
    for pattern, fix in _RULES:
        if pattern.search(blob):
            return fix
    return _GENERIC


__all__ = ["suggest", "suggest_action_chips"]
