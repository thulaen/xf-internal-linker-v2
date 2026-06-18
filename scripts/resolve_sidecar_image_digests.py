"""Resolve sidecar image tags to digest-pinned lockfile entries."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCKFILE = ROOT / "sidecar-images.lock.json"
SIDECARS = ("streamd", "startupd", "sidecars")
DIGEST_RE = re.compile(r"\bsha256:[0-9a-f]{64}\b")
PINNED_RE = re.compile(r"^[^:@/]+(?::[0-9]+)?/.+@sha256:[0-9a-f]{64}$")


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run docker buildx imagetools inspect for one image."""
    return subprocess.run(args, check=False, capture_output=True, text=True, timeout=60)


def parse_digest(output: str) -> str:
    """Return the first sha256 digest from docker image inspection output."""
    match = DIGEST_RE.search(output)
    if not match:
        raise ValueError("docker did not return a sha256 digest")
    return match.group(0)


def pin_image_reference(image: str, digest: str) -> str:
    """Return a registry image reference pinned by digest."""
    clean_image = image.strip()
    if not clean_image:
        raise ValueError("image reference is empty")
    if "@" in clean_image:
        candidate = clean_image
    else:
        slash_index = clean_image.rfind("/")
        colon_index = clean_image.rfind(":")
        base = clean_image[:colon_index] if colon_index > slash_index else clean_image
        candidate = f"{base}@{digest}"
    if not PINNED_RE.match(candidate):
        raise ValueError("image must be registry/path@sha256:<64 lowercase hex>")
    return candidate


def resolve_images(
    images: dict[str, str],
    runner: CommandRunner = default_runner,
) -> dict[str, str]:
    """Resolve the requested sidecar image references to pinned references."""
    pinned: dict[str, str] = {}
    for name in SIDECARS:
        image = images.get(name, "").strip()
        if not image:
            raise ValueError(f"{name} image reference is missing")
        if "@" in image:
            pinned[name] = pin_image_reference(image, "")
            continue
        completed = runner(["docker", "buildx", "imagetools", "inspect", image])
        output = f"{completed.stdout}\n{completed.stderr}"
        if completed.returncode != 0:
            raise ValueError(f"docker could not inspect {name} image {image}: {_first_line(output)}")
        pinned[name] = pin_image_reference(image, parse_digest(output))
    return pinned


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


def write_lockfile(path: Path, payload: dict[str, str]) -> None:
    """Write the sidecar lockfile with stable key order."""
    path.write_text(json.dumps({name: payload[name] for name in SIDECARS}, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve Slice 20 sidecar images to digests.")
    parser.add_argument("--streamd", default="", help="streamd image tag or digest reference.")
    parser.add_argument("--startupd", default="", help="startupd image tag or digest reference.")
    parser.add_argument("--sidecars", default="", help="sidecars image tag or digest reference.")
    parser.add_argument("--lockfile", type=Path, default=DEFAULT_LOCKFILE)
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved lockfile without writing it.")
    args = parser.parse_args(argv)

    try:
        resolved = resolve_images(
            {"streamd": args.streamd, "startupd": args.startupd, "sidecars": args.sidecars}
        )
    except ValueError as exc:
        print(f"FAIL: {exc}")
        print("[SIDECAR DIGEST RESOLVE: no]")
        return 1

    if args.dry_run:
        print(json.dumps(resolved, indent=2))
    else:
        write_lockfile(args.lockfile, resolved)
        print(f"Wrote {args.lockfile}")
    print("[SIDECAR DIGEST RESOLVE: yes]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
