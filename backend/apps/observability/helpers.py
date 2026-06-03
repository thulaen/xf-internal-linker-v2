from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"/\d+(?=/|$)")
_UUID_RE = re.compile(r"/[0-9a-f]{8}-[0-9a-f-]{27,36}(?=/|$)", re.I)


def bucket_url_label(path: str) -> str:
    cleaned = (path or "/").split("?", 1)[0].strip() or "/"
    cleaned = _UUID_RE.sub("/:uuid", cleaned)
    cleaned = _NUMBER_RE.sub("/:id", cleaned)
    return cleaned[:160]

