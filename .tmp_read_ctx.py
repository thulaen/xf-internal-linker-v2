from pathlib import Path
import sys


def show_tail(path: str, label: str, lines: int = 80) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"--- {label} ---")
    for line in text[-lines:]:
        safe_line = line.encode("utf-8", errors="backslashreplace").decode("utf-8", errors="ignore")
        print(safe_line)
    print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    show_tail("AGENT-HANDOFF.md", "AGENT-HANDOFF.md")
    show_tail("AI-CONTEXT.md", "AI-CONTEXT.md")
    show_tail("audit/agent_progress_latest.txt", "agent_progress_latest.txt", lines=20)


if __name__ == "__main__":
    main()
