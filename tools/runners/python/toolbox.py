"""Tool dispatcher for the Python runner image (ADR 0010, SLICE-23).

Usage inside the image (the image entrypoint is this dispatcher):

    /opt/runner/toolbox pytest -q <targets>
    /opt/runner/toolbox ruff check <paths>
    /opt/runner/toolbox mutmut run

Pure-Python tools (pytest, mypy, coverage, mutmut, bandit) run via
``runpy`` (i.e. ``python -m <tool>``) off the py_binary launcher's sys.path,
which carries all the locked wheels in one runfiles tree. ruff is a Rust binary
(its wheel shim can't find the binary under rules_python's layout), so it ships
as a standalone binary on PATH and is exec'd directly — keeping one consistent
``toolbox <tool> <args>`` interface for the shard wrapper (SLICE-27).
"""

import os
import runpy
import shutil
import sys

# Tools shipped as standalone binaries on PATH, not as importable modules.
_BINARY_TOOLS = {"ruff"}


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: toolbox <tool> [args...]\n")
        return 2
    tool = sys.argv[1]
    args = sys.argv[2:]
    if tool in _BINARY_TOOLS:
        path = shutil.which(tool) or "/usr/local/bin/" + tool
        os.execv(path, [tool] + args)  # replaces this process; never returns
    # Pure-Python tool: behave exactly like `python -m <tool> <args>`.
    sys.argv = [tool] + args
    runpy.run_module(tool, run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
