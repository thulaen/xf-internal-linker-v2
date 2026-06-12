#!/usr/bin/env python3
"""Command line entrypoint for the inter-model AutoIssue pool."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from inter_model_interface import DEFAULT_DB_PATH, InterModelInterface

AGENT_NAMES = ("codex", "claude", "gemini", "antigravity")


def _agent_name(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in AGENT_NAMES:
        choices = ", ".join(AGENT_NAMES)
        raise argparse.ArgumentTypeError(
            f"unknown agent '{value}'. Use one of: {choices}"
        )
    return normalized


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite state path.")
    sub = parser.add_subparsers(dest="command", required=True)

    join = sub.add_parser("join", help="Join the 2-minute sprint pool.")
    join.add_argument("--agent", required=True, type=_agent_name)

    sub.add_parser("status", help="Show the active sprint pool.")

    say = sub.add_parser("say", help="Post a short note for other agents.")
    say.add_argument("--agent", required=True, type=_agent_name)
    say.add_argument("--text", required=True, help="Plain-English note for teammates.")

    messages = sub.add_parser("messages", help="Read recent notes from other agents.")
    messages.add_argument("--limit", type=int, default=10)

    heartbeat = sub.add_parser("heartbeat", help="Say this agent is still alive.")
    heartbeat.add_argument("--agent", required=True, type=_agent_name)
    heartbeat.add_argument(
        "--state",
        default="active",
        choices=["active", "thinking", "working", "testing", "reviewing", "blocked", "possibly_idle"],
    )
    heartbeat.add_argument("--detail", default="")

    cleanup = sub.add_parser("cleanup-stale", help="Mark quiet agents idle or stale.")
    cleanup.add_argument("--max-age-seconds", type=int, default=900)
    cleanup.add_argument("--idle-after-seconds", type=int, default=300)

    claim = sub.add_parser("claim-next", help="Claim one picked AutoIssue safely.")
    claim.add_argument("--agent", required=True, type=_agent_name)
    claim.add_argument("--issue", required=True, type=int)
    claim.add_argument("--path", action="append", required=True, help="Touched file or folder.")

    add_path = sub.add_parser("add-path", help="Add extra touched paths to an owned claim.")
    add_path.add_argument("--agent", required=True, type=_agent_name)
    add_path.add_argument("--issue", required=True, type=int)
    add_path.add_argument("--path", action="append", required=True, help="Newly discovered file or folder.")

    fixed = sub.add_parser("mark-fixed", help="Mark one claimed AutoIssue fixed.")
    fixed.add_argument("--agent", required=True, type=_agent_name)
    fixed.add_argument("--issue", required=True, type=int)

    review = sub.add_parser("review", help="Record a cross-review vote.")
    review.add_argument("--agent", required=True, type=_agent_name)
    review.add_argument("--issue", required=True, type=int)
    review.add_argument("--vote", required=True, choices=["pass", "needs-correction"])
    review.add_argument("--note", default="")

    sub.add_parser("recommend-commit-agent", help="Recommend who should stage after review.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    store = InterModelInterface(Path(args.db))
    if args.command == "join":
        result = store.join(args.agent)
        print(f"{result.message} Team size is {result.team_size}. Wait 10 minutes for teammates.")
    elif args.command == "status":
        print(store.status_summary())
    elif args.command == "say":
        print(store.post_message(args.agent, args.text))
    elif args.command == "messages":
        rows = store.recent_messages(limit=args.limit)
        if rows:
            print("\n".join(rows))
        else:
            print("No intermodel messages recorded.")
    elif args.command == "heartbeat":
        store.heartbeat(args.agent, state=args.state, detail=args.detail)
        print(f"{args.agent} heartbeat recorded as {args.state}.")
    elif args.command == "cleanup-stale":
        stale = store.cleanup_stale_agents(
            max_age_seconds=args.max_age_seconds,
            idle_after_seconds=args.idle_after_seconds,
        )
        if stale:
            print("Marked stale and released locks for: " + ", ".join(stale))
        else:
            print("No stale agents found.")
    elif args.command == "claim-next":
        result = store.claim_issue(args.agent, args.issue, args.path)
        print(result.message)
        return 0 if result.claimed else 1
    elif args.command == "add-path":
        result = store.add_touched_paths(args.agent, args.issue, args.path)
        print(result.message)
        return 0 if result.claimed else 1
    elif args.command == "mark-fixed":
        if store.mark_fixed(args.agent, args.issue):
            print(f"{args.agent} marked AutoIssue #{args.issue} fixed.")
        else:
            print(f"{args.agent} cannot mark AutoIssue #{args.issue} fixed because it does not own it.")
            return 1
    elif args.command == "review":
        if store.review_issue(args.agent, args.issue, args.vote, args.note):
            print(f"{args.agent} recorded review for AutoIssue #{args.issue}: {args.vote}.")
        else:
            print(f"{args.agent} cannot review AutoIssue #{args.issue} in the current review phase.")
            return 1
    elif args.command == "recommend-commit-agent":
        rec = store.recommend_commit_agent()
        print(rec.reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
