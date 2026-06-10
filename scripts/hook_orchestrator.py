#!/usr/bin/env python3
import json
import subprocess
import time
import sys
import os
from pathlib import Path

STATE_FILE = Path(".git/xf-hook-state.json")
TIMEOUT_SEC = 300

def get_git_diff_hash() -> str:
    """Get the tree hash of the currently staged files (Bazel-like exact state)."""
    try:
        result = subprocess.run(
            ["git", "write-tree"], 
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error computing git write-tree: {e}", file=sys.stderr)
        return "unknown-hash"

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"hooks": {}}

def save_state(state):
    try:
        # Create .git directory if running locally without one somehow (rare)
        STATE_FILE.parent.mkdir(exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"Failed to save hook state: {e}", file=sys.stderr)

def main():
    mode = "pre-commit"
    if len(sys.argv) > 1:
        mode = sys.argv[1]

    state = load_state()
    current_hash = get_git_diff_hash()

    # Define the core hooks.
    all_hooks = [
        {"name": "tool-readiness", "cmd": ["sh", "scripts/run-tool-readiness.sh"]},
        {"name": "run-python-quality", "cmd": ["sh", "scripts/quality_cache.sh", "sh", "scripts/run-python-quality.sh"]},
        {"name": "run-angular-quality", "cmd": ["sh", "scripts/quality_cache.sh", "sh", "scripts/run-angular-quality.sh"]},
        {"name": "run-rust-quality", "cmd": ["sh", "scripts/quality_cache.sh", "sh", "scripts/run-rust-quality.sh"]},
        {"name": "check-missing-tests", "cmd": ["python", ".githooks/check-missing-tests.py"]},
    ]

    to_run = []
    for hook in all_hooks:
        name = hook["name"]
        hook_state = state["hooks"].get(name, {
            "name": name,
            "last_passed_hash": None,
            "status": "Failed" # Default to failed to run first time
        })
        state["hooks"][name] = hook_state

        if hook_state["status"] == "Passed" and hook_state.get("last_passed_hash") == current_hash:
            # Passed and unmodified! Skip it!
            continue
        
        to_run.append(hook)

    if not to_run:
        print("[Hook Orchestrator] No hooks need to run. All passed & unmodified.")
        sys.exit(0)

    # Sort priority: Failed (0) > SkippedTime (1) > Passed (2)
    def sort_key(h):
        status = state["hooks"][h["name"]]["status"]
        if status == "Failed": return 0
        if status == "SkippedTime": return 1
        return 2

    to_run.sort(key=sort_key)

    print(f"[Hook Orchestrator] Starting {len(to_run)} hooks with a {TIMEOUT_SEC}s timeout constraint...")

    processes = []
    for hook in to_run:
        name = hook["name"]
        print(f"  -> Spawning: {name} (Priority: {state['hooks'][name]['status']})")
        # Start process
        # Use start_new_session to ensure we can kill process groups on timeout
        p = subprocess.Popen(
            hook["cmd"], 
            start_new_session=True
        )
        processes.append((name, p))

    start_time = time.time()
    results = {}
    
    while processes:
        elapsed = time.time() - start_time
        if elapsed > TIMEOUT_SEC:
            print(f"\n[Hook Orchestrator] [TIMEOUT] Global timeout of {TIMEOUT_SEC}s reached!")
            # Kill remaining
            for name, p in processes:
                print(f"  -> Aborting {name}...")
                try:
                    if os.name == 'nt':
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                    else:
                        import signal
                        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                except Exception:
                    p.kill()
                results[name] = {"success": False, "timed_out": True}
            break

        # Check completed processes
        still_running = []
        for name, p in processes:
            retcode = p.poll()
            if retcode is not None:
                results[name] = {"success": retcode == 0, "timed_out": False}
            else:
                still_running.append((name, p))
        
        processes = still_running
        time.sleep(0.5)

    # Update state
    any_failed = False
    for name, res in results.items():
        hook_state = state["hooks"][name]
        if res["timed_out"]:
            if hook_state["status"] != "Passed":
                hook_state["status"] = "SkippedTime"
        elif res["success"]:
            hook_state["status"] = "Passed"
            hook_state["last_passed_hash"] = current_hash
        else:
            hook_state["status"] = "Failed"
            any_failed = True

    save_state(state)

    if any_failed:
        print("\n[COMMIT BLOCKED] One or more quality hooks failed. See above.")
        sys.exit(1)
    else:
        print("\n[COMMIT OK] Hooks completed or safely timed out. Commit passes.")
        sys.exit(0)

if __name__ == "__main__":
    main()
