"""Tests for the language-ownership gate.

Each case writes a tiny file into the repo tree under a temp-named path,
runs scan_paths(), then removes it — scan_paths reads from disk relative to
REPO_ROOT, so the files must exist for the duration of the assertion.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("check-language-ownership.py")
spec = importlib.util.spec_from_file_location("check_language_ownership", MODULE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

REPO_ROOT = hook.REPO_ROOT


class _TempFile:
    def __init__(self, rel: str, content: str) -> None:
        self.rel = rel
        self.path = REPO_ROOT / rel
        self.content = content

    def __enter__(self) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.content, encoding="utf-8")
        return self.rel

    def __exit__(self, *exc) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass
        # Prune now-empty temp parent dirs so the repo tree stays clean and
        # leftover dirs never trip the Rule K go-service-contract scan.
        parent = self.path.parent
        while parent != REPO_ROOT and parent.is_dir():
            try:
                next(parent.iterdir())
                break  # not empty
            except StopIteration:
                parent.rmdir()
                parent = parent.parent
            except OSError:
                break


class LanguageOwnershipTests(unittest.TestCase):
    def test_python_minhash_reimpl_flagged(self) -> None:
        code = "def compute_minhash(rows):\n    return [hash(r) % 97 for r in rows]\n"
        with _TempFile("backend/apps/zz_tmp/badhash.py", code) as rel:
            self.assertTrue(hook.scan_paths([rel]))

    def test_python_minhash_ok_when_delegating(self) -> None:
        code = (
            "import papertrail_dedup\n"
            "def compute_minhash(rows):\n"
            "    return papertrail_dedup.minhash(rows)\n"
        )
        with _TempFile("backend/apps/zz_tmp/okhash.py", code) as rel:
            self.assertEqual(hook.scan_paths([rel]), [])

    def test_python_http_server_flagged(self) -> None:
        code = "from flask import Flask\napp = Flask(__name__)\n"
        with _TempFile("backend/apps/zz_tmp/server.py", code) as rel:
            self.assertTrue(hook.scan_paths([rel]))

    def test_django_views_not_flagged_for_http(self) -> None:
        # views.py is the legitimate Django HTTP surface — must not flag.
        code = "from rest_framework.response import Response\n"
        with _TempFile("backend/apps/zz_tmp/views.py", code) as rel:
            self.assertEqual(hook.scan_paths([rel]), [])

    def test_python_classifier_in_services_flagged(self) -> None:
        code = (
            "def classify_severity(score):\n"
            "    if score >= 0.9:\n        return 'critical'\n"
            "    if score >= 0.5:\n        return 'high'\n"
            "    return 'low'\n"
        )
        with _TempFile("backend/apps/zz_tmp/services/sev.py", code) as rel:
            self.assertTrue(hook.scan_paths([rel]))

    def test_plain_orchestration_not_flagged(self) -> None:
        code = "def fetch(ids):\n    return [i for i in ids if i]\n"
        with _TempFile("backend/apps/zz_tmp/services/plain.py", code) as rel:
            self.assertEqual(hook.scan_paths([rel]), [])

    def test_go_service_postgres_flagged(self) -> None:
        code = (
            "package main\n"
            "type Row struct {\n\tID int `db:\"id\"`\n}\n"
            "func main() { sql.Open(\"postgres\", \"\") }\n"
        )
        with _TempFile("services/zz_tmp/main.go", code) as rel:
            self.assertTrue(hook.scan_paths([rel]))

    def test_go_service_no_postgres_ok(self) -> None:
        code = "package main\nfunc main() { println(\"ok\") }\n"
        with _TempFile("services/zz_tmp/clean.go", code) as rel:
            self.assertEqual(hook.scan_paths([rel]), [])

    def test_generated_go_skipped(self) -> None:
        code = "package gen\ntype Row struct { ID int `db:\"id\"` }\n"
        with _TempFile("services/zz_tmp/api/gen/x.pb.go", code) as rel:
            self.assertEqual(hook.scan_paths([rel]), [])

    def test_fail_message_has_three_parts(self) -> None:
        with patch.object(hook.sys.stderr, "write") as werr:
            hook._fail(["v: bad"])
        written = "".join(c.args[0] for c in werr.call_args_list)
        self.assertIn("FAIL check-language-ownership", written)
        self.assertIn("WHY:", written)
        self.assertIn("UNBLOCK:", written)


if __name__ == "__main__":
    unittest.main()
