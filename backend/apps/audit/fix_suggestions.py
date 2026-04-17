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
        re.compile(r"ConnectionError.*redis|Redis.*refused|redis.*ConnectionError", re.I),
        "Redis is down. Run `docker compose restart redis`.",
    ),
    (
        re.compile(r"psycopg|OperationalError.*database|could not connect to server", re.I),
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

_GENERIC = (
    "Open the 'Copy for AI' button on this error, paste the prompt into "
    "Claude or Codex, and let it propose a fix. Include the GlitchTip link "
    "if present."
)


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


__all__ = ["suggest"]
