"""Tests for scoping the FAISS single-worker startup check."""

from django.test import SimpleTestCase

from apps.pipeline.apps import _should_assert_faiss_single_worker


class FaissReadyScopeTests(SimpleTestCase):
    def test_skips_normal_management_commands(self) -> None:
        self.assertFalse(_should_assert_faiss_single_worker(["manage.py", "shell"]))

    def test_skips_default_only_celery_worker(self) -> None:
        argv = ["celery", "-A", "config.celery", "worker", "-Q", "default"]
        self.assertFalse(_should_assert_faiss_single_worker(argv))

    def test_asserts_pipeline_worker(self) -> None:
        argv = ["celery", "-A", "config.celery", "worker", "-Q", "pipeline,embeddings"]
        self.assertTrue(_should_assert_faiss_single_worker(argv))

    def test_asserts_unknown_worker_queues(self) -> None:
        self.assertTrue(_should_assert_faiss_single_worker(["celery", "worker"]))
