#!/usr/bin/env python3
"""Long-running watcher that enforces TDD/KISS/DRY on source changes.

The agent-guard container runs this module. It watches the source directories
and runs the per-file checks from ``agent_guard.py`` whenever a watched file
changes. The rule logic itself lives in ``agent_guard.py`` and is reused here so
the daemon and the one-shot CLI stay in sync.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent_guard  # noqa: E402  (path insert must precede import)
from watchdog.events import FileSystemEventHandler  # noqa: E402
from watchdog.observers import Observer  # noqa: E402

DEBOUNCE_SECONDS = 1.0
POLL_SECONDS = 1.0


class GuardEventHandler(FileSystemEventHandler):
    """Runs agent_guard checks on changed source files, debounced per path."""

    def __init__(self, debounce_seconds=DEBOUNCE_SECONDS):
        self._debounce = debounce_seconds
        self._last_seen = {}

    def should_check(self, path, now=None):
        if not path.endswith(agent_guard.FILE_EXTS):
            return False
        now = time.time() if now is None else now
        if now - self._last_seen.get(path, 0.0) > self._debounce:
            return False
        self._last_seen[path] = now
        return True

    def handle(self, path):
        if not self.should_check(path):
            return
        agent_guard.build_dry_index(exclude_files=[path])
        last_test_mod_time = agent_guard.get_last_test_mod_time()
        agent_guard.process_file_checks(path, last_test_mod_time)

    def on_modified(self, event):
        if not event.is_directory:
            self.handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.handle(event.src_path)


def watched_dirs():
    return [d for d in agent_guard.WATCH_DIRS if os.path.isdir(d)]


def main():
    observer = Observer()
    handler = GuardEventHandler()
    directories = watched_dirs()
    for directory in directories:
        observer.schedule(handler, directory, recursive=True)
    print(
        f"agent_guard_daemon watching: {', '.join(directories) or '(none found)'}",
        flush=True,
    )
    observer.start()
    try:
        while True:
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
