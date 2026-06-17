#!/usr/bin/env python3
"""Cross-agent progress + stuck reporter — Claude / Codex / Gemini / Antigravity.

WHY THIS EXISTS
    The user is a non-coder who wants a single, always-truthful status line while
    ANY agent works: how much uncommitted work is left, and — most importantly —
    whether something has silently stalled. This command computes that line from
    live repository state so no agent has to remember to type it by hand, and so
    every agent (not just one tool) reports the same way.

HOW AGENTS USE IT
    Start a user-requested task with ``--start-task`` and a pipe-separated
    ``--steps`` list, move the task with ``--step`` / ``--status``, and close it
    with ``--finish-task``. If at least ten minutes have passed since the last
    printed line (or anything looks stuck), it prints a ``[PROGRESS ...]`` block;
    otherwise it stays quiet so quick back-to-back replies are not spammed. A
    stuck condition ALWAYS prints, even inside the ten-minute window, because a
    silent stall is the thing we most need to surface. ``--force`` prints
    regardless of the cadence.

WHAT "STUCK" MEANS HERE
    The exact failure we keep hitting: a quality/mutation Docker container that has
    been up for several minutes at near-zero CPU (a blocked wait, not real work),
    or a mutation lock file held far longer than a run should take. Both are
    reported in plain English. A warm helper whose only job is to idle (for
    example ``tail -f /dev/null``) sits at ~0% CPU on purpose, so it is never
    counted as stuck — that would be a false alarm that hides real stalls.

Plain-English only in all output — define nothing in jargon. No network calls.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "audit" / "agent_progress_state.json"
STATUS_PATH = REPO_ROOT / "audit" / "agent_progress_latest.txt"
TASK_STATE_PATH = REPO_ROOT / "audit" / "agent_progress_task_state.json"
MUTATION_LOCK = REPO_ROOT / ".git" / "xf-scoped-mutation.lock"

CADENCE_SECONDS = 600            # ten-minute refresh tick
TASK_STALE_SECONDS = 45 * 60     # after 45 minutes, old chat task progress expires
STUCK_CONTAINER_MINUTES = 8      # a quality/mutation container up this long...
STUCK_CPU_PERCENT = 5.0          # ...at under this CPU is a blocked wait, not work
STUCK_LOCK_MINUTES = 8           # a mutation lock held longer than this is suspect
_BAR_WIDTH = 20
_STEP_STATUSES = {"pending", "in_progress", "done", "blocked"}


# ── pure helpers (no I/O — unit-tested without Docker or git) ─────────────────
def progress_bar(done: int, total: int) -> str:
    """A 20-cell text bar. Empty when there is no known starting total."""
    if total <= 0:
        return "░" * _BAR_WIDTH
    pct = max(0, min(100, round(100 * done / total)))
    filled = pct * _BAR_WIDTH // 100
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def percent_done(dirty: int, baseline: int) -> int:
    """Percent of the starting dirty-file count that is now committed."""
    if baseline <= 0:
        return 0
    return max(0, min(100, round(100 * (baseline - dirty) / baseline)))


def split_steps(raw_steps: str) -> list[str]:
    """Split a pipe-separated step list into clean step names."""
    return [step.strip() for step in raw_steps.split("|") if step.strip()]


def start_task_state(title: str, steps: list[str], now: float) -> dict:
    """Create chat-relative progress state from the user's requested task."""
    clean_steps = [step.strip() for step in steps if step.strip()]
    if not clean_steps:
        clean_steps = ["Work"]
    task_steps = [
        {"name": step, "status": "in_progress" if index == 0 else "pending"}
        for index, step in enumerate(clean_steps)
    ]
    return {
        "title": (title or "working").strip() or "working",
        "steps": task_steps,
        "started_at": now,
        "updated_at": now,
        "finished": False,
    }


def active_task_or_none(task: dict | None, now: float) -> dict | None:
    """Return active chat task state, or None when it is missing, done, or stale."""
    if not task or task.get("finished"):
        return None
    updated_at = float(task.get("updated_at", 0.0) or 0.0)
    if updated_at <= 0 or now - updated_at > TASK_STALE_SECONDS:
        return None
    return task


def update_task_step_state(task: dict, step_name: str, status: str, now: float) -> dict:
    """Update one chat-task step while keeping other step decisions intact."""
    if status not in _STEP_STATUSES:
        raise ValueError(f"Unknown progress step status: {status}")
    clean_step = step_name.strip()
    if not clean_step:
        raise ValueError("Progress step name cannot be empty")
    updated = {**task, "steps": [dict(step) for step in task.get("steps", [])]}
    matching_step = None
    for step in updated["steps"]:
        if step.get("name") == clean_step:
            matching_step = step
            break
    if matching_step is None:
        matching_step = {"name": clean_step, "status": "pending"}
        updated["steps"].append(matching_step)
    if status == "in_progress":
        for step in updated["steps"]:
            if step is not matching_step and step.get("status") == "in_progress":
                step["status"] = "pending"
    matching_step["status"] = status
    updated["updated_at"] = now
    updated["finished"] = False
    return updated


def finish_task_state(task: dict, now: float) -> dict:
    """Mark every chat-task step done and close the active task."""
    updated = {**task, "steps": [dict(step) for step in task.get("steps", [])]}
    for step in updated["steps"]:
        step["status"] = "done"
    updated["updated_at"] = now
    updated["finished"] = True
    return updated


def chat_task_counts(task: dict) -> tuple[int, int]:
    """Completed and total step counts for the active chat task."""
    steps = task.get("steps", [])
    done = sum(1 for step in steps if step.get("status") == "done")
    return done, len(steps)


def chat_task_current_step(task: dict) -> str:
    """Human-readable current step for the task progress line."""
    steps = task.get("steps", [])
    for wanted_status in ("blocked", "in_progress", "pending"):
        for step in steps:
            if step.get("status") == wanted_status:
                return str(step.get("name", "work"))
    return "complete"


def chat_task_stuck_reasons(task: dict | None) -> list[str]:
    """Stuck reasons produced by the chat task itself."""
    if not task:
        return []
    for step in task.get("steps", []):
        if step.get("status") == "blocked":
            return [f"current chat task is blocked at {step.get('name', 'work')}"]
    return []


def _chat_task_line(task: dict) -> str:
    done, total = chat_task_counts(task)
    pct = 0 if total <= 0 else max(0, min(100, round(100 * done / total)))
    noun = "step" if total == 1 else "steps"
    return (
        f"Task   [{progress_bar(done, total)}] {pct}%   {done}/{total} {noun} done "
        f"· current: {chat_task_current_step(task)}"
    )


# Container commands meaning "stay alive doing nothing" — a warm helper kept
# running so a later ``docker exec`` starts fast. Such a container idles at ~0%
# CPU by design, so it must never be mistaken for a stalled job.
_KEEPALIVE_MARKERS = ("tail -f", "sleep infinity")


def is_keepalive_command(command: str) -> bool:
    """True when a container's command just idles forever (a warm helper)."""
    cmd = (command or "").lower()
    return any(marker in cmd for marker in _KEEPALIVE_MARKERS)


def detect_stuck(containers: list[dict], lock_age_seconds: float | None) -> list[str]:
    """Plain-English list of stalls. ``containers`` is name/up_minutes/cpu_percent/keepalive."""
    stuck: list[str] = []
    for c in containers:
        if c.get("keepalive"):
            continue  # warm idle helper — 0% CPU is by design, not a stall
        if c["up_minutes"] >= STUCK_CONTAINER_MINUTES and c["cpu_percent"] < STUCK_CPU_PERCENT:
            stuck.append(
                f"{c['name']} has been busy {int(c['up_minutes'])} min but is using "
                f"{c['cpu_percent']:.0f}% processor — it looks stalled, not working"
            )
    if lock_age_seconds is not None and lock_age_seconds >= STUCK_LOCK_MINUTES * 60:
        stuck.append(
            f"the mutation-test lock has been held {int(lock_age_seconds // 60)} min — "
            "a run may be wedged"
        )
    return stuck


def should_emit(last_emitted_at: float | None, now: float, stuck: bool, force: bool) -> bool:
    """Emit on force, on any stall, or once the ten-minute tick elapses."""
    if force or stuck:
        return True
    if last_emitted_at is None:
        return True
    return (now - last_emitted_at) >= CADENCE_SECONDS


def render(
    now_hms: str,
    label: str,
    dirty: int,
    baseline: int,
    stuck: list[str],
    task: dict | None = None,
) -> str:
    """Build the [PROGRESS ...] block shown to the user."""
    title = str(task.get("title", label)) if task else label
    lines = [f"[PROGRESS · {now_hms} · {title}]"]
    if task:
        lines.append(_chat_task_line(task))
        lines.append(f"Repo   {dirty} uncommitted files total")
    elif baseline > 0:
        done = max(0, baseline - dirty)
        pct = percent_done(dirty, baseline)
        bar = progress_bar(done, baseline)
        lines.append(
            f"Work   [{bar}] {pct}%   {dirty} files left to commit (started at {baseline})"
        )
    else:
        lines.append("Task   no active chat task")
        lines.append(f"Repo   {dirty} uncommitted files total")
    if stuck:
        lines.append("Stuck? YES — " + "; ".join(stuck))
    else:
        lines.append("Stuck? no — nothing stalled")
    return "\n".join(lines)


# ── thin I/O wrappers (kept tiny so the pure helpers above carry the logic) ───
def _git_dirty_count() -> int:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout
    return sum(1 for ln in out.splitlines() if ln.strip())


def _docker_quality_containers() -> list[dict]:
    """name/up_minutes/cpu_percent/keepalive for running quality/mutation containers."""
    names = subprocess.run(
        ["docker", "ps", "--no-trunc", "--format", "{{.Names}}\t{{.RunningFor}}\t{{.Command}}"],
        capture_output=True, text=True, check=False,
    ).stdout
    rows: list[dict] = []
    targets: dict[str, dict] = {}
    for ln in names.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        name, running_for, command = parts[0], parts[1], "\t".join(parts[2:])
        if not any(k in name for k in ("mutation", "quality", "mutmut")):
            continue
        targets[name] = {
            "up_minutes": _minutes_from_running_for(running_for),
            "keepalive": is_keepalive_command(command),
        }
    if not targets:
        return rows
    stats = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}", *targets],
        capture_output=True, text=True, check=False,
    ).stdout
    cpu: dict[str, float] = {}
    for ln in stats.splitlines():
        if "\t" not in ln:
            continue
        name, perc = ln.split("\t", 1)
        cpu[name] = float(perc.strip().rstrip("%") or 0.0)
    for name, meta in targets.items():
        rows.append({
            "name": name,
            "up_minutes": meta["up_minutes"],
            "cpu_percent": cpu.get(name, 0.0),
            "keepalive": meta["keepalive"],
        })
    return rows


def _minutes_from_running_for(text: str) -> float:
    """Best-effort parse of Docker's 'Up 11 minutes'-style RunningFor string."""
    text = text.lower()
    num = "".join(ch for ch in text if ch.isdigit())
    value = float(num) if num else 0.0
    if "hour" in text:
        return value * 60
    if "second" in text:
        return value / 60
    return value


def _lock_age_seconds(now: float) -> float | None:
    if not MUTATION_LOCK.exists():
        return None
    return now - MUTATION_LOCK.stat().st_mtime


def _read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_task_state() -> dict:
    try:
        return json.loads(TASK_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _write_task_state(state: dict) -> None:
    TASK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _write_status_file(text: str) -> None:
    """Write the latest [PROGRESS] block so ANY agent can read + surface it.

    This is the cross-agent hand-off: the background scheduler and every agent
    keep this one file current, and each agent simply prints its contents at the
    start of a reply. That is what makes Claude / Codex / Gemini / Antigravity
    all show the identical pulse without re-deriving it.
    """
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass


def _notify_stuck(stuck: list[str]) -> None:
    """Best-effort Windows desktop balloon when something is stalled.

    Fired by the scheduled task so a stall is visible even when no agent is
    replying. Never raises — a missing PowerShell or headless session is fine.
    """
    message = (" | ".join(stuck))[:240].replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Warning;"
        "$n.BalloonTipTitle='XF Linker - something is stuck';"
        f"$n.BalloonTipText='{message}';"
        "$n.Visible=$true;$n.ShowBalloonTip(10000);Start-Sleep -Seconds 6;$n.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, timeout=20, check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass


def _configure_stdout() -> None:
    # Windows consoles default to cp1252, which cannot encode the bar glyphs
    # (█ ░). Force UTF-8 so the same output renders on every agent's platform.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Cross-agent progress + stuck reporter.")
    ap.add_argument("--label", default="working", help="short plain-English task label")
    ap.add_argument(
        "--baseline",
        type=int,
        default=0,
        help="starting dirty-file count for the % bar",
    )
    ap.add_argument("--start-task", default="", help="start chat-relative task progress")
    ap.add_argument("--steps", default="", help="pipe-separated steps for --start-task")
    ap.add_argument("--step", default="", help="chat task step to update")
    ap.add_argument(
        "--status",
        choices=sorted(_STEP_STATUSES),
        default="in_progress",
        help="status for --step",
    )
    ap.add_argument("--finish-task", action="store_true", help="mark the active chat task complete")
    ap.add_argument("--force", action="store_true", help="print even inside the 10-minute window")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print but do not write the state or status file",
    )
    ap.add_argument(
        "--background",
        action="store_true",
        help=(
            "scheduler mode: refresh the shared status file and alert on a stall, "
            "without printing to chat or consuming the ten-minute chat throttle"
        ),
    )
    ap.add_argument(
        "--notify-on-stuck",
        action="store_true",
        help="fire a desktop alert when something is stalled",
    )
    return ap


def _baseline_from_state(args: argparse.Namespace, state: dict, dirty: int) -> int:
    baseline = args.baseline or int(state.get("baseline", 0))
    return baseline or dirty


def _apply_task_args(
    args: argparse.Namespace, task_state: dict, now: float
) -> tuple[dict, dict | None, bool]:
    changed_task_state = False
    display_task = active_task_or_none(task_state, now)
    if args.start_task:
        task_state = start_task_state(args.start_task, split_steps(args.steps), now)
        display_task = task_state
        changed_task_state = True
    if args.step:
        base_task = display_task or start_task_state(args.label, [args.step], now)
        task_state = update_task_step_state(base_task, args.step, args.status, now)
        display_task = task_state
        changed_task_state = True
    if args.finish_task and display_task:
        task_state = finish_task_state(display_task, now)
        display_task = task_state
        changed_task_state = True

    return task_state, display_task, changed_task_state


def main() -> int:
    _configure_stdout()
    args = _build_parser().parse_args()
    now = time.time()
    state = _read_state()
    dirty = _git_dirty_count()
    baseline = _baseline_from_state(args, state, dirty)
    task_state, display_task, changed_task_state = _apply_task_args(
        args, _read_task_state(), now
    )
    stuck = detect_stuck(_docker_quality_containers(), _lock_age_seconds(now))
    stuck.extend(chat_task_stuck_reasons(display_task))
    now_hms = time.strftime("%H:%M:%S", time.localtime(now))
    block = render(now_hms, args.label, dirty, baseline, stuck, display_task)

    # The status file always holds the freshest computed state, so any agent can
    # read + surface it. Both the background scheduler and an agent refresh it.
    if not args.dry_run:
        _write_status_file(block)
        if changed_task_state:
            _write_task_state(task_state)

    if args.background:
        # Agent-independent refresh (the Scheduled Task path): keep the file
        # current and alert on a stall, but never print to chat and never
        # consume the chat throttle — that is reserved for an agent actually
        # showing the line to the user.
        if stuck and args.notify_on_stuck:
            _notify_stuck(stuck)
        return 0

    # Agent reply mode: show the line in chat, throttled to ten minutes.
    if not should_emit(state.get("last_emitted_at"), now, bool(stuck), args.force):
        return 0
    print(block)
    if not args.dry_run:
        _write_state({"last_emitted_at": now, "baseline": baseline})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
