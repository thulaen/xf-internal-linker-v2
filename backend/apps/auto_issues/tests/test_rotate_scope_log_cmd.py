from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase


class RotateScopeLogTestCase(SimpleTestCase):
    def test_rotate_scope_log_missing(self):
        with TemporaryDirectory() as temp_dir:
            out = StringIO()
            call_command("rotate_scope_log", repo_root=temp_dir, stdout=out)
            self.assertIn("[SCOPE LOG ROTATED: skipped missing log]", out.getvalue())

    def test_rotate_scope_log_empty(self):
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            log_path = repo_root / "audit" / "scope_decisions.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.touch()
            
            out = StringIO()
            call_command("rotate_scope_log", repo_root=str(repo_root), stdout=out)
            self.assertIn("[SCOPE LOG ROTATED: skipped empty log]", out.getvalue())

    def test_rotate_scope_log_success(self):
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            log_path = repo_root / "audit" / "scope_decisions.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("dummy content")
            
            out = StringIO()
            call_command("rotate_scope_log", repo_root=str(repo_root), stdout=out)
            self.assertIn("[SCOPE LOG ROTATED: archived=", out.getvalue())
            self.assertTrue(log_path.exists())
            self.assertEqual(log_path.stat().st_size, 0)
