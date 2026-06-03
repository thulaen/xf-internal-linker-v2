import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "enumerate_failed_jobs.py"
_spec = importlib.util.spec_from_file_location("enumerate_failed_jobs", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class EnumerateFailedJobsTests(unittest.TestCase):
    def test_extract_jobs_from_dict(self):
        payload = {"jobs": [{"id": 1}, {"id": 2}]}
        self.assertEqual(mod._extract_jobs(payload), [{"id": 1}, {"id": 2}])

    def test_extract_jobs_from_list(self):
        payload = [{"jobs": [{"id": 1}]}, {"jobs": [{"id": 2}]}]
        self.assertEqual(mod._extract_jobs(payload), [{"id": 1}, {"id": 2}])

    def test_extract_jobs_raises_on_invalid(self):
        with self.assertRaises(RuntimeError):
            mod._extract_jobs("invalid")

    def test_first_failed_step_name_finds_failed_step(self):
        job = {
            "name": "job1",
            "steps": [
                {"name": "step1", "conclusion": "success"},
                {"name": "step2", "conclusion": "failure"},
            ]
        }
        self.assertEqual(mod.first_failed_step_name(job), "step2")

    def test_first_failed_step_name_fallback_to_job_name(self):
        job = {"name": "job1", "steps": []}
        self.assertEqual(mod.first_failed_step_name(job), "job1")

    def test_default_error_excerpt(self):
        job = {"name": "Build", "html_url": "http://example.com"}
        excerpt = mod.default_error_excerpt(job, "Compile")
        self.assertEqual(excerpt, "Build failed at Compile; see job http://example.com")

    def test_command_args_formatting(self):
        job = {"name": "Test Job"}
        args = mod._command_args("123", job, "Step 1", "Error here", "CI", "owner/repo")
        expected = [
            "--run-id", "123",
            "--job-name", "Test Job",
            "--step", "Step 1",
            "--error-excerpt", "Error here",
            "--workflow", "CI",
            "--repo", "owner/repo"
        ]
        self.assertEqual(args, expected)

if __name__ == "__main__":
    unittest.main()
