#!/usr/bin/env python3
"""Verify every runner image in runner-images.lock.json (ADR 0010, SLICE-23).

For each runner it asserts:
  * the recorded identity is a sha256 DIGEST pin (never a floating tag), and
  * that digest actually resolves in the registry (the manifest is present and
    its Docker-Content-Digest matches the lockfile).

Run it on a host that can reach the Mint registry (e.g. Dell):
    python tools/runners/verify_lockfile.py
Exit code 0 = all good; 1 = a drift/missing/floating entry (fail-closed).

Standard library only (urllib) so it can run inside the slim runner images.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

from image_refs import LOCKFILE, image_ref, load_lockfile, runner_entries

_MANIFEST_ACCEPT = (
    "application/vnd.oci.image.manifest.v1+json,"
    "application/vnd.oci.image.index.v1+json,"
    "application/vnd.docker.distribution.manifest.v2+json"
)


def _registry_digest(repository: str, digest: str, timeout: int = 10) -> str:
    """Return the registry's Docker-Content-Digest for repository@digest, or ''."""
    host, path = repository.split("/", 1)
    url = f"http://{host}/v2/{path}/manifests/{digest}"
    req = urllib.request.Request(url, headers={"Accept": _MANIFEST_ACCEPT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - homelab HTTP registry
        return resp.headers.get("Docker-Content-Digest", "")


def verify(lockfile: Path = LOCKFILE) -> int:
    try:
        runners = runner_entries(load_lockfile(lockfile))
    except ValueError as exc:
        print(f"FAIL verify_lockfile: {exc}")
        return 1
    ok = True
    for name, entry in sorted(runners.items()):
        try:
            got = _registry_digest(entry["repository"], entry["digest"])
        except (urllib.error.URLError, OSError) as exc:
            print(f"FAIL {name}: cannot reach {image_ref(entry)}: {exc}")
            ok = False
            continue
        if got == entry["digest"]:
            print(f"OK   {name}: {image_ref(entry)} resolves")
        else:
            print(f"FAIL {name}: registry returned {got!r}, lockfile has {entry['digest']!r}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(verify())
