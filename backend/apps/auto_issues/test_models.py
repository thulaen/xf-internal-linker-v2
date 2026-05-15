from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssueCategory


class AutoIssueCategoryModelTests(SimpleTestCase):
    def test_category_string_uses_label(self) -> None:
        category = AutoIssueCategory(key="correctness", label="Correctness")

        self.assertEqual(str(category), "Correctness")

    def test_empty_description_is_allowed_for_boundary_categories(self) -> None:
        category = AutoIssueCategory(key="uncategorized", label="Uncategorized")

        self.assertEqual(category.description, "")
