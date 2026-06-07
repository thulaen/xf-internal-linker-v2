"""Route Docker builds to the right builder before running them."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "docker-build-routing.json"

CommandRunner = Callable[[list[str]], tuple[int, str, str]]
# Streams a built image from one Docker context to another (save | load).
# Injectable so tests can assert transfers without moving real image bytes.
TransferFn = Callable[[str, str, str], tuple[int, str]]


def _default_runner(command: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode, completed.stdout, completed.stderr


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select the safest Docker builder, then run docker compose build.",
    )
    parser.add_argument("--target", action="append", default=[], help="Compose service to build.")
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


def _split_machines(config: dict) -> tuple[list[tuple[str, int]], str]:
    """Return ``([(builder_name, percent), ...], salt)`` with percents summing to 100.

    Two config shapes are accepted so the split can grow past two machines
    without breaking older configs:

      * N-ary (current): ``compilation_split.machines`` is a list of
        ``{"key", "builder", "percent"}`` entries, e.g. Dell 88 / Mint 8 /
        Windows 4. The order of the list defines the cumulative hash ranges.
      * Legacy two-machine: ``compilation_split.mint_percent`` +
        ``windows_percent`` (kept so an old config still routes correctly).
    """
    split = config.get("compilation_split") or {}
    salt = str(split.get("salt", "smart-build-v1"))
    machines = split.get("machines")
    if machines:
        weighted = [
            (str(entry.get("builder") or entry.get("key")), int(entry.get("percent", 0)))
            for entry in machines
        ]
        if sum(percent for _builder, percent in weighted) != 100:
            raise ValueError("Build split machines must add up to 100 percent.")
        return weighted, salt
    builders = config.get("builders") or {}
    mint_percent = int(split.get("mint_percent", 65))
    windows_percent = int(split.get("windows_percent", 35))
    if mint_percent + windows_percent != 100:
        raise ValueError("Build split must add up to 100 percent.")
    weighted = [
        (builders.get("mint") or builders.get("general") or "mint", mint_percent),
        (builders.get("windows") or "desktop-linux", windows_percent),
    ]
    return weighted, salt


def _builder_name(config: dict, key: str) -> str:
    builders = config.get("builders") or {}
    if key == "mint":
        return builders.get("mint") or builders.get("general") or "mint"
    if key == "windows":
        return builders.get("windows") or "desktop-linux"
    return str(builders[key])


def _select_builder_for_target(target: str, config: dict) -> str:
    """Deterministically route one target to a builder by stable weighted hash.

    The same ``salt:target`` always lands in the same 0-99 bucket, and the
    bucket falls into one machine's cumulative range — so the split is stable
    across runs and machines (no central coordinator needed). With Dell at 88,
    Mint at 8, Windows at 4: buckets 0-87 → Dell, 88-95 → Mint, 96-99 → Windows.
    """
    weighted, salt = _split_machines(config)
    digest = hashlib.sha256(f"{salt}:{target}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    cumulative = 0
    for builder, percent in weighted:
        cumulative += percent
        if bucket < cumulative:
            return builder
    return weighted[-1][0]


def _build_groups(targets: Sequence[str], config: dict) -> dict[str, list[str]]:
    if not targets:
        return {_select_builder_for_target("__all__", config): []}
    groups: dict[str, list[str]] = {}
    for target in targets:
        groups.setdefault(_select_builder_for_target(target, config), []).append(target)
    return groups


def _ensure_builder(builder: str, runner: CommandRunner) -> bool:
    code, _out, _err = runner(["docker", "buildx", "inspect", builder])
    return code == 0


def _plain_error(message: str) -> None:
    print(message, file=sys.stderr)


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _report_build_failure(
    *,
    builder: str,
    targets: Sequence[str],
    command: Sequence[str],
    exit_code: int,
    out: str,
    err: str,
    config: dict,
    runner: CommandRunner,
) -> None:
    settings = config.get("failure_autoissues") or {}
    if not settings.get("enabled", True):
        return
    limit = int(settings.get("max_output_chars", 12000))
    payload = {
        "builder": builder,
        "targets": list(targets) or ["<all>"],
        "command": list(command),
        "exit_code": int(exit_code),
        "stdout": _trim(out, limit),
        "stderr": _trim(err, limit),
    }
    report_command = [
        "docker", "compose", "exec", "-T", "backend", "python", "manage.py",
        "ingest_build_failure_autoissue", "--payload-json",
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    ]
    code, _report_out, report_err = runner(report_command)
    if code != 0:
        _plain_error(
            "Build failed, and the AutoIssue report could not be saved. "
            f"Reporter error: {report_err.strip() or 'unknown error'}"
        )


def _transfer_image(image: str, src_builder: str, dst_builder: str) -> tuple[int, str]:
    """Stream a built image from one Docker context to another: save | load.

    `docker --context mint compose build` builds on Mint's daemon, so the image
    only exists on Mint. This streams it into the local (Windows) daemon so the
    65/35 mint-first split never leaves an image stranded. Streaming (a pipe,
    not a temp tar) keeps big images off disk.
    """
    import time
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            saver = subprocess.Popen(
                ["docker", "--context", src_builder, "save", image],
                stdout=subprocess.PIPE,
            )
            loader = subprocess.Popen(
                ["docker", "--context", dst_builder, "load"],
                stdin=saver.stdout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            if saver.stdout is not None:
                saver.stdout.close()
            out_bytes, _ = loader.communicate(timeout=600)
            saver.wait()
            rc = loader.returncode if loader.returncode else saver.returncode
            if rc == 0:
                return rc, (out_bytes.decode("utf-8", "replace") if out_bytes else "")
            else:
                err_msg = out_bytes.decode("utf-8", "replace") if out_bytes else ""
                if attempt < max_retries:
                    _plain_error(f"[smart-build] transfer failed (attempt {attempt}/{max_retries}), retrying in 5s... Error: {err_msg}")
                    time.sleep(5)
                else:
                    return rc, err_msg
        except OSError as exc:
            if attempt < max_retries:
                _plain_error(f"[smart-build] transfer failed with OSError (attempt {attempt}/{max_retries}), retrying in 5s... Error: {exc}")
                time.sleep(5)
            else:
                return 1, f"transfer failed: {exc}"
    return 1, "transfer failed: max retries exceeded"


def _service_image_map(runner: CommandRunner) -> dict[str, str]:
    """Return {compose-service: image-tag} from `docker compose config`.

    Returns {} on any failure or non-JSON output, so callers (and tests with a
    stub runner) degrade gracefully to "no transfer".
    """
    code, out, _err = runner(["docker", "compose", "config", "--format", "json"])
    if code != 0 or not (out or "").strip():
        return {}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {}
    services = data.get("services") or {}
    return {
        name: str(svc["image"])
        for name, svc in services.items()
        if isinstance(svc, dict) and svc.get("image")
    }


def _load_images_locally(
    *,
    builder: str,
    targets: Sequence[str],
    config: dict,
    runner: CommandRunner,
    transfer: TransferFn,
) -> int:
    """Pull images built on a remote builder back into the local Docker.

    No-op when the build ran on the local (Windows) builder, or when
    `load_remote_images` is disabled in the routing config.
    """
    local = _builder_name(config, "windows")
    if builder == local or not config.get("load_remote_images", True):
        return 0
    if targets and any("mutation-tools" in t for t in targets):
        print(f"[smart-build] Skipping local load for {targets} because they are remote-only mutation tools.", file=sys.stderr)
        return 0
    image_map = _service_image_map(runner)
    tags = [image_map[t] for t in targets if t in image_map] if targets else list(image_map.values())
    rc = 0
    for tag in tags:
        _plain_error(f"[smart-build] loading {tag} from {builder} into {local} (mint-first --load)...")
        code, out = transfer(tag, builder, local)
        if out:
            print(out, end="", file=sys.stderr)
        if code != 0:
            _plain_error(
                f"[smart-build] FAILED to load {tag} into {local} (exit {code}). "
                f"It built on {builder} but is not available locally."
            )
            rc = code or 1
    return rc


def _run_build_for_group(
    *,
    builder: str,
    targets: Sequence[str],
    build_args: Sequence[str],
    config: dict,
    runner: CommandRunner,
    transfer: TransferFn,
) -> int:
    command = ["docker", "--context", builder, "compose", "build", *build_args, *targets]
    result, out, err = runner(command)
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if result != 0:
        _report_build_failure(
            builder=builder,
            targets=targets,
            command=command,
            exit_code=result,
            out=out,
            err=err,
            config=config,
            runner=runner,
        )
        return result
    return _load_images_locally(
        builder=builder, targets=targets, config=config, runner=runner, transfer=transfer,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner = _default_runner,
    transfer: TransferFn = _transfer_image,
) -> int:
    args = _parse_args(list(argv or []))
    config = _load_config(Path(args.config))
    build_args = _normalise_build_args(args.build_args)
    targets = list(args.target)
    groups = _build_groups(targets, config)

    for builder in groups:
        if _ensure_builder(builder, runner):
            continue
        if builder == _builder_name(config, "windows"):
            _plain_error(
                f"Windows builder is not available: {builder}. "
                "The build was stopped so it cannot silently use a paid builder."
            )
        else:
            label = "Mint" if builder == "mint" else builder.capitalize()
            _plain_error(
                f"{label} builder is not available: {builder}. "
                "The build was stopped so it cannot silently fall back to another "
                "machine or Docker Build Cloud."
            )
        return 2

    if args.select_only:
        for builder, group_targets in groups.items():
            label = ", ".join(group_targets) if group_targets else "<all>"
            print(f"Selected Docker builder: {builder} for {label}")
        return 0

    for builder, group_targets in groups.items():
        result = _run_build_for_group(
            builder=builder,
            targets=group_targets,
            build_args=build_args,
            config=config,
            runner=runner,
            transfer=transfer,
        )
        if result != 0:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
