"""Render digest-pinned runner image references from runner-images.lock.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


LOCKFILE = Path(__file__).resolve().parents[2] / "runner-images.lock.json"
REQUIRED_RUNNERS = ("merge", "node-browser", "python", "rust")
_SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def load_lockfile(path: Path = LOCKFILE) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    runners = data.get("runners")
    if not isinstance(runners, dict) or not runners:
        raise ValueError("runner image lockfile has no runners")
    return data


def runner_entries(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    runners = data["runners"]
    missing = sorted(set(REQUIRED_RUNNERS) - set(runners))
    if missing:
        raise ValueError(f"runner image lockfile missing runners: {', '.join(missing)}")
    return {name: _validated_entry(name, entry) for name, entry in runners.items()}


def image_ref(entry: dict[str, str]) -> str:
    return f"{entry['repository']}@{entry['digest']}"


def refs_by_runner(path: Path = LOCKFILE) -> dict[str, str]:
    entries = runner_entries(load_lockfile(path))
    return {name: image_ref(entries[name]) for name in sorted(entries)}


def render_env(refs: dict[str, str]) -> str:
    lines = []
    for name, ref in sorted(refs.items()):
        env_name = name.upper().replace("-", "_")
        lines.append(f"XF_RUNNER_{env_name}_IMAGE={ref}")
    return "\n".join(lines) + "\n"


def render_configmap(refs: dict[str, str], *, name: str, namespace: str) -> str:
    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {namespace}",
        "data:",
    ]
    lines.extend(f"  {runner}.image: {ref}" for runner, ref in sorted(refs.items()))
    return "\n".join(lines) + "\n"


def _validated_entry(name: str, entry: Any) -> dict[str, str]:
    if not isinstance(entry, dict):
        raise ValueError(f"{name}: lockfile entry must be an object")
    repository = _required_text(name, entry, "repository")
    digest = _required_text(name, entry, "digest")
    if ":" in repository.rsplit("/", 1)[-1]:
        raise ValueError(f"{name}: repository must not include a tag")
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError(f"{name}: digest must be sha256 plus 64 lowercase hex characters")
    return {"repository": repository, "digest": digest}


def _required_text(name: str, entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: missing {key}")
    return value.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lockfile", type=Path, default=LOCKFILE)
    parser.add_argument("--format", choices=("env", "json", "configmap"), default="env")
    parser.add_argument("--configmap-name", default="runner-image-refs")
    parser.add_argument("--namespace", default="xf-test")
    return parser


def main() -> int:
    args = _parser().parse_args()
    refs = refs_by_runner(args.lockfile)
    if args.format == "json":
        print(json.dumps(refs, indent=2, sort_keys=True))
    elif args.format == "configmap":
        print(render_configmap(refs, name=args.configmap_name, namespace=args.namespace), end="")
    else:
        print(render_env(refs), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
