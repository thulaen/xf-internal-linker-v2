#!/usr/bin/env python
"""Run the Lua PreToolUse advisor through local Docker Desktop."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
ADVISOR = "apps/governance/lua_runtime/advisors/workflow_state_reminder.lua"
ADVISOR_TIMEOUT_SECONDS = 15
STALE_PAYLOAD_SECONDS = 600
LUA_DRIVER = r"""
local advisor_path = os.getenv("XF_LUA_ADVISOR_PATH")
local payload_path = os.getenv("XF_LUA_PAYLOAD_FILE")
local function read_file(path)
  if not path or path == "" then
    return ""
  end
  local handle = io.open(path, "rb")
  if not handle then
    return ""
  end
  local data = handle:read("*a")
  handle:close()
  return data or ""
end
local function file_exists(path)
  local handle = io.open(path, "rb")
  if handle then
    handle:close()
    return true
  end
  return false
end
local payload = read_file(payload_path)
local advisor, err = loadfile(advisor_path)
if not advisor then
  io.stderr:write("LuaAdvisorUnavailableError: " .. tostring(err) .. "\n")
  os.exit(0)
end
local module = advisor()
module.run({
  fs = { exists = file_exists },
  tool_call = { read = function() return payload end },
  advisor = {
    remind = function(message) io.stderr:write(tostring(message) .. "\n") end,
    exit = function() return 0 end,
  },
})
os.exit(0)
"""
REMOTE_MARKERS = (
    "mint",
    "dell",
    "ssh://",
    "tcp://10.10.10.91:2376",
    "tcp://192.168.0.91:2376",
)


def _remote_docker_is_active() -> bool:
    docker_host = os.environ.get("DOCKER_HOST", "").lower()
    docker_context = os.environ.get("DOCKER_CONTEXT", "").lower()
    if docker_host:
        return True
    return bool(docker_context and docker_context != "desktop-linux")


def _remote_detail() -> str:
    values = " ".join(
        value.lower()
        for value in (
            os.environ.get("DOCKER_HOST", ""),
            os.environ.get("DOCKER_CONTEXT", ""),
        )
    )
    for marker in REMOTE_MARKERS:
        if marker in values:
            return marker
    return "remote Docker context"


def _run_advisor(agent: str, payload: str) -> None:
    env = os.environ.copy()
    env["DOCKER_CONTEXT"] = "desktop-linux"
    env.pop("DOCKER_HOST", None)
    env["XF_LUA_ADVISOR_AGENT"] = agent
    env["XF_LUA_ADVISOR_PATH"] = f"/repo/{ADVISOR}"
    payload_dir = ROOT / "tmp"
    payload_dir.mkdir(parents=True, exist_ok=True)
    _prune_stale_payload_files(payload_dir)
    payload_file = payload_dir / f"lua-advisor-payload-{uuid.uuid4().hex}.json"
    payload_file.write_text(payload, encoding="utf-8")
    env["XF_LUA_PAYLOAD_FILE"] = f"/repo/tmp/{payload_file.name}"
    process = subprocess.Popen(
        [
            "docker",
            "--context",
            "desktop-linux",
            "run",
            "--rm",
            "-e",
            "XF_LUA_ADVISOR_AGENT",
            "-e",
            "XF_LUA_ADVISOR_PATH",
            "-e",
            "XF_LUA_PAYLOAD_FILE",
            "-v",
            f"{ROOT}:/repo",
            "-w",
            "/repo",
            "xf-linker-lua-quality-tools:latest",
            "luajit",
            "-e",
            LUA_DRIVER,
            ADVISOR,
        ],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        stdout, stderr = process.communicate("", timeout=ADVISOR_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        else:
            process.kill()
        payload_file.unlink(missing_ok=True)
        print("LuaAdvisorUnavailableError: Docker Desktop advisor run timed out", file=sys.stderr)
        return
    if stdout:
        print(stdout, end="", file=sys.stderr)
    if stderr:
        print(stderr, end="", file=sys.stderr)
    if process.returncode != 0:
        print(f"LuaAdvisorUnavailableError: advisor exited {process.returncode}", file=sys.stderr)
    payload_file.unlink(missing_ok=True)


def _prune_stale_payload_files(payload_dir: Path) -> None:
    cutoff = time.time() - STALE_PAYLOAD_SECONDS
    for path in payload_dir.glob("lua-advisor-payload-*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _read_payload(timeout_seconds: float = 1.0) -> str:
    output: Queue[str] = Queue(maxsize=1)

    def read_stdin() -> None:
        output.put(sys.stdin.read())

    reader = Thread(target=read_stdin, daemon=True)
    reader.start()
    reader.join(timeout_seconds)
    if reader.is_alive():
        return ""
    return output.get_nowait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=("claude", "codex", "gemini"), required=True)
    args = parser.parse_args()
    payload = _read_payload()
    if _remote_docker_is_active():
        print(f"LuaAdvisorUnavailableError: refused {_remote_detail()}; use desktop-linux", file=sys.stderr)
        return 0
    try:
        _run_advisor(args.agent, payload)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"LuaAdvisorUnavailableError: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
