"""Tests for migration data-preservation guardrails."""

from django.test import SimpleTestCase

from apps.core.services.data_preservation import scan_migration_text


class MigrationSafetyScannerTests(SimpleTestCase):
    def test_blocks_full_table_delete(self):
        findings = scan_migration_text(
            "backend/apps/content/migrations/9999_bad.py",
            "PassageEmbedding.objects.all().delete()",
        )

        self.assertEqual(findings[0].kind, "full table delete")

    def test_blocks_vector_nulling(self):
        findings = scan_migration_text(
            "backend/apps/content/migrations/9999_bad.py",
            "ContentItem.objects.update(embedding=None)",
        )

        self.assertEqual(findings[0].kind, "vector nulling")

    def test_blocks_raw_table_drop(self):
        findings = scan_migration_text(
            "backend/apps/content/migrations/9999_bad.py",
            'migrations.RunSQL("DROP TABLE content_contentitem")',
        )

        self.assertEqual(findings[0].kind, "raw drop/truncate")

    def test_blocks_artifact_model_without_identity_fields(self):
        findings = scan_migration_text(
            "backend/apps/content/migrations/9999_bad.py",
            """
            migrations.CreateModel(
                name="ExtraEmbedding",
                fields=[("vector", models.JSONField(default=list))],
            )
            """,
        )

        self.assertEqual(findings[0].kind, "duplicate artifact risk")

    def test_allows_artifact_model_with_hash_and_version_fields(self):
        findings = scan_migration_text(
            "backend/apps/content/migrations/9999_good.py",
            """
            migrations.CreateModel(
                name="BoundedEmbedding",
                fields=[
                    ("vector", models.JSONField(default=list)),
                    ("content_hash", models.CharField(max_length=64)),
                    ("signal_version", models.CharField(max_length=64)),
                ],
            )
            """,
        )

        self.assertEqual(findings, [])
