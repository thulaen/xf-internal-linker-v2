#!/usr/bin/env python3
"""Cross-agent real-time progress streamer — Claude / Codex / Gemini / Antigravity.

This script polls for active quality/mutation containers on the remote Dell helper
machine and streams their standard output continuously. It runs as a background task
so that AI agents and the user can see real-time output in the async task UI.
"""
import time
import subprocess
import sys

def get_active_container() -> tuple[str, str] | None:
    result = subprocess.run(
        ["docker", "--context", "dell", "ps", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        cid, name = parts[0], parts[1]
        image = parts[2] if len(parts) > 2 else ""
        searchable = f"{name} {image}".lower()
        if any(k in searchable for k in ("mutation", "quality", "mutmut", "stryker", "compiled_tools", "compiled-tools")):
            return cid, name
    return None

def stream_logs(cid: str, name: str) -> None:
    print(f"\n=======================================================", flush=True)
    print(f" [STREAM] Attached to {name} ({cid})", flush=True)
    print(f"=======================================================\n", flush=True)
    
    proc = subprocess.Popen(
        ["docker", "--context", "dell", "logs", "-f", "--tail", "50", cid],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1, # Line buffered
        encoding='utf-8',
        errors='replace'
    )
    
    try:
        # Read lines interactively and flush them to UI
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                sys.stdout.write(line)
                sys.stdout.flush()
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        raise

def main() -> int:
    print("Starting Live Stream Monitor...", flush=True)
    print("Waiting for active quality/mutation containers on Dell...", flush=True)
    
    seen = set()
    try:
        while True:
            active = get_active_container()
            if active:
                cid, name = active
                if cid not in seen:
                    stream_logs(cid, name)
                    seen.add(cid)
                    print(f"\n[STREAM] Detached from {name} (container exited or finished).", flush=True)
                    print("Waiting for next active container...", flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nLive Stream Monitor stopped.", flush=True)
        return 0
    return 0

if __name__ == "__main__":
    sys.exit(main())
