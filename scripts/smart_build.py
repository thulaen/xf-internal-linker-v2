"""Route Docker builds to the right builder before running them."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "docker-build-routing.json"
GPU_CHECK_IMAGE = "nvidia/cuda:12.4.1-base-ubuntu22.04"

CommandRunner = Callable[[list[str]], tuple[int, str, str]]


def _default_runner(command: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select the safest Docker builder, then run docker compose build.",
    )
    parser.add_argument("--target", action="append", default=[], help="Compose service to build.")
    parser.add_argument("--gpu", action="store_true", help="Force local GPU builder routing.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the smart build routing JSON file.",
    )
    parser.add_argument(
        "--select-only",
        action="store_true",
        help="Select and verify the builder without starting a Docker build.",
    )
    parser.add_argument(
        "build_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed to docker compose build after --.",
    )
    return parser.parse_args(argv)


def _normalise_build_args(args: Sequence[str]) -> list[str]:
    if args and args[0] == "--":
        return list(args[1:])
    return list(args)


def _needs_gpu(targets: Sequence[str], build_args: Sequence[str], forced: bool, config: dict) -> bool:
    if forced:
        return True
    gpu_targets = set(config.get("gpu_targets") or [])
    if any(target in gpu_targets for target in targets):
        return True
    joined = " ".join(build_args).lower()
    return any(token in joined for token in ("enable_gpu=1", "cuda=1", "use_gpu=true"))


def _ensure_builder(builder: str, runner: CommandRunner) -> bool:
    code, _out, _err = runner(["docker", "buildx", "inspect", builder])
    return code == 0


def _ensure_gpu(runner: CommandRunner) -> bool:
    code, _out, _err = runner(
        [
            "docker",
            "--context",
            "desktop-linux",
            "run",
            "--rm",
            "--gpus=all",
            GPU_CHECK_IMAGE,
            "nvidia-smi",
        ]
    )
    return code == 0


def _plain_error(message: str) -> None:
    print(message, file=sys.stderr)


def run(argv: Sequence[str] | None = None, *, runner: CommandRunner = _default_runner) -> int:
    args = _parse_args(list(argv or []))
    config = _load_config(Path(args.config))
    build_args = _normalise_build_args(args.build_args)
    targets = list(args.target)
    gpu_build = _needs_gpu(targets, build_args, args.gpu, config)
    builders = config["builders"]
    builder = builders["gpu_local"] if gpu_build else builders["general"]

    if not _ensure_builder(builder, runner):
        if gpu_build:
            _plain_error(
                f"Local GPU builder is not available: {builder}. "
                "The build was stopped so it cannot silently use a paid or disk-heavy builder."
            )
        else:
            _plain_error(
                f"Mint builder is not available: {builder}. "
                "The build was stopped so it cannot silently fall back to Windows or Docker Build Cloud."
            )
        return 2

    if gpu_build and not _ensure_gpu(runner):
        _plain_error(
            "Local GPU check failed. The build was stopped because GPU-only images must be "
            "built and proven on the local GPU path."
        )
        return 2

    if args.select_only:
        print(f"Selected Docker builder: {builder}")
        return 0

    command = ["docker", "--context", builder, "compose", "build", *build_args, *targets]
    result, out, err = runner(command)
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
