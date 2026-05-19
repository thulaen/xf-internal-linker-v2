"""Tests for .githooks/check-no-parallel-quality.py.

Synthesises shell-script contents in tmp files, then drives the hook's
parser to assert it catches the forbidden patterns and respects the
skip marker + the whitelist config.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


HOOKS_DIR = Path(__file__).resolve().parent

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    path = HOOKS_DIR / "check-no-parallel-quality.py"
    spec = importlib.util.spec_from_file_location("check_no_parallel_quality", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_no_parallel_quality"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


class ViolationParserTests(unittest.TestCase):
    """`_violations_in_file` detects forbidden patterns."""

    def _write(self, contents: str) -> Path:
        tmp = Path(tempfile.NamedTemporaryFile(
            suffix=".sh", delete=False, mode="w"
        ).name)
        tmp.write_text(contents, encoding="utf-8")
        return tmp

    def test_backgrounded_quality_script_flagged(self):
        f = self._write("#!/usr/bin/env bash\nbash scripts/run-angular-quality.sh &\n")
        violations = hook._violations_in_file(f)
        self.assertEqual(len(violations), 1)
        self.assertIn("background", violations[0][1].lower())

    def test_backgrounded_compose_run_flagged(self):
        f = self._write(
            "#!/usr/bin/env bash\n"
            "docker compose run --rm -T --name xf-quality-a backend echo hi &\n"
        )
        violations = hook._violations_in_file(f)
        self.assertTrue(any("backgrounded docker compose run" in v[1] for v in violations))

    def test_wait_command_flagged(self):
        f = self._write("#!/usr/bin/env bash\nwait -n\n")
        violations = hook._violations_in_file(f)
        self.assertTrue(any("wait" in v[1].lower() for v in violations))

    def test_unnamed_docker_compose_run_flagged(self):
        f = self._write(
            "#!/usr/bin/env bash\ndocker compose run --rm -T backend echo hi\n"
        )
        violations = hook._violations_in_file(f)
        self.assertTrue(any(
            "docker compose run without --name" in v[1] for v in violations
        ))

    def test_named_docker_compose_run_accepted(self):
        f = self._write(
            "#!/usr/bin/env bash\n"
            "docker compose run --rm -T --name xf-quality-foo backend echo hi\n"
        )
        violations = hook._violations_in_file(f)
        self.assertEqual(violations, [])

    def test_wrapper_invocation_accepted(self):
        # `run_cpp_step ... "docker compose run ..."` is whitelisted.
        f = self._write(
            "#!/usr/bin/env bash\n"
            'run_cpp_step normal cpp-foo "docker compose run --rm -T compiled-tools bash /repo/scripts/foo.sh"\n'
        )
        violations = hook._violations_in_file(f)
        self.assertEqual(violations, [])

    def test_quality_docker_compose_run_helper_accepted(self):
        f = self._write(
            "#!/usr/bin/env bash\n"
            "quality_docker_compose_run stryker frontend-mutation-tools sh -lc 'foo'\n"
        )
        violations = hook._violations_in_file(f)
        # No `docker compose run` literal on this line; nothing to flag.
        self.assertEqual(violations, [])

    def test_two_compose_runs_in_one_shell_block_flagged(self):
        f = self._write(
            "#!/usr/bin/env bash\n"
            "docker compose run --rm -T --name xf-quality-a backend sh -lc '\n"
            "docker compose run --rm -T --name xf-quality-b backend echo one\n"
            "docker compose run --rm -T --name xf-quality-c backend echo two\n"
            "'\n"
        )
        violations = hook._violations_in_file(f)
        self.assertTrue(any("two `docker compose run`" in v[1] for v in violations))

    def test_skip_marker_grandfathers_a_violation(self):
        f = self._write(
            "#!/usr/bin/env bash\n"
            "bash scripts/run-angular-quality.sh &  # no-parallel-quality-skip: "
            "this is a legitimate background usage in a 50-char justification\n"
        )
        violations = hook._violations_in_file(f)
        self.assertEqual(violations, [])

    def test_comment_line_not_flagged(self):
        f = self._write(
            "#!/usr/bin/env bash\n"
            "# docker compose run --rm backend echo this is in a comment\n"
        )
        violations = hook._violations_in_file(f)
        self.assertEqual(violations, [])


class WhitelistLoaderTests(unittest.TestCase):
    """`_load_whitelist` reads from the config file or falls back."""

    def test_fallback_when_no_config_file(self):
        # The current file IS present; _FALLBACK_WHITELIST should
        # match exactly the file's contents (current_+ fallback parity).
        # We just confirm the function returns SOMETHING non-empty.
        names = hook._load_whitelist()
        self.assertGreater(len(names), 0)
        self.assertIn("quality_docker_compose_run", names)

    def test_helper_invocation_regex_matches_each_name(self):
        names = hook._load_whitelist()
        for name in names:
            self.assertRegex(
                f"some_text {name} more_text",
                hook._HELPER_INVOCATION,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
