import importlib
from django.test import TestCase
from django.apps import apps

class TestMigrations00140015(TestCase):
    def test_0014_has_sonarqube(self):
        """Given migration 0014, when we check choices, then sonarqube is present."""
        mig_0014 = importlib.import_module("apps.auto_issues.migrations.0014_add_sonarqube_source")
        choices_dict = dict(mig_0014.SOURCE_CHOICES)
        self.assertIn("sonarqube", choices_dict)

    def test_0015_seed_categories(self):
        """Given migration 0015, when executed, it creates the expected categories."""
        mig_0015 = importlib.import_module("apps.auto_issues.migrations.0015_seed_rust_defect_categories")
        mig_0015.seed_categories(apps, None)
        category_model = apps.get_model("auto_issues", "AutoIssueCategory")
        self.assertTrue(category_model.objects.filter(key="runtime-pressure").exists())
        self.assertTrue(category_model.objects.filter(key="mutation-survivor").exists())
