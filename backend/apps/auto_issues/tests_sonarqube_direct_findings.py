"""Static regression tests for current direct SonarQube findings."""

from pathlib import Path

from django.test import SimpleTestCase


def _repo_root() -> Path:
    for candidate in (Path("/repo"), Path(__file__).resolve().parents[3]):
        if (candidate / "frontend").exists():
            return candidate
    return Path(__file__).resolve().parents[3]


REPO_ROOT = _repo_root()


class SonarQubeDirectFindingTests(SimpleTestCase):
    def _read(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def test_suggestions_migration_reuses_recommended_setting_keys(self):
        source = self._read(
            "backend/apps/suggestions/migrations/0017_refresh_recommended_feature_flags.py"
        )

        for setting_key in (
            "silo.mode",
            "ga4_gsc.ranking_weight",
            "explore_exploit.enabled",
            "explore_exploit.ranking_weight",
            "explore_exploit.exploration_rate",
        ):
            with self.subTest(setting_key=setting_key):
                self.assertEqual(1, source.count(f'"{setting_key}"'))

    def test_suggestions_content_item_relation_uses_one_model_constant(self):
        source = self._read("backend/apps/suggestions/models.py")

        self.assertEqual(1, source.count('"content.ContentItem"'))
        self.assertIn("CONTENT_ITEM_MODEL", source)

    def test_initial_suggestions_migration_reuses_timestamp_help_constants(self):
        source = self._read("backend/apps/suggestions/migrations/0001_initial.py")

        self.assertEqual(1, source.count('"Timestamp when this record was created."'))
        self.assertEqual(
            1,
            source.count('"Timestamp when this record was last modified."'),
        )
        self.assertIn("CREATED_AT_HELP", source)
        self.assertIn("UPDATED_AT_HELP", source)

    def test_early_suggestions_migrations_reuse_content_item_constant(self):
        for path in (
            "backend/apps/suggestions/migrations/0001_initial.py",
            "backend/apps/suggestions/migrations/0002_rename_diag_run_reason_idx_suggestions_pipelin_a2cf09_idx_and_more.py",
        ):
            with self.subTest(path=path):
                source = self._read(path)
                self.assertEqual(1, source.count('"content.contentitem"'))
                self.assertIn("CONTENT_ITEM_MODEL", source)
