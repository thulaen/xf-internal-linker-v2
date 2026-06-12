from django.test import SimpleTestCase
from apps.auto_issues.models import AutoIssue

class TestIssue522(SimpleTestCase):
    def test_autoissue_abstract_removed(self):
        """Given the AutoIssue model, when instantiated with 'abstract', then it raises TypeError."""
        with self.assertRaises(TypeError):
            AutoIssue(abstract="This should fail")
