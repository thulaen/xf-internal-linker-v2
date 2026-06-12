import hashlib
from django.test import SimpleTestCase
from apps.auto_issues.services.codeql import _project_severity, _fingerprint, CodeQLFinding
from apps.auto_issues.models import AutoIssue

class CodeQLImportTests(SimpleTestCase):
    def test_project_severity_numeric_bands(self):
        # 8.0/6.0 numeric bands
        # Score >= 8 -> CRITICAL
        self.assertEqual(_project_severity({}, {"properties": {"security-severity": "8.5"}}), AutoIssue.SEVERITY_CRITICAL)
        self.assertEqual(_project_severity({}, {"properties": {"security-severity": 8}}), AutoIssue.SEVERITY_CRITICAL)
        
        # Score >= 6 -> HIGH
        self.assertEqual(_project_severity({}, {"properties": {"security-severity": "7.5"}}), AutoIssue.SEVERITY_HIGH)
        self.assertEqual(_project_severity({}, {"properties": {"security-severity": 6}}), AutoIssue.SEVERITY_HIGH)
    
    def test_project_severity_level_fallback(self):
        # The level fallback map
        self.assertEqual(_project_severity({"level": "error"}, {}), AutoIssue.SEVERITY_HIGH)
        self.assertEqual(_project_severity({"level": "warning"}, {}), AutoIssue.SEVERITY_MEDIUM)
        self.assertEqual(_project_severity({"level": "note"}, {}), AutoIssue.SEVERITY_LOW)
        self.assertEqual(_project_severity({"level": "unknown"}, {}), AutoIssue.SEVERITY_MEDIUM)
        
        # Default when missing is 'warning' -> 'medium'
        self.assertEqual(_project_severity({}, {}), AutoIssue.SEVERITY_MEDIUM)

    def test_deterministic_fingerprint(self):
        finding = CodeQLFinding(
            language="python",
            rule_id="py/test-rule",
            file_path="src/main.py",
            line=42,
            message="Test message",
            severity="high",
            recommendation="Fix it"
        )
        fp = _fingerprint(finding)
        
        expected_raw = "python|py/test-rule|src/main.py|42|Test message"
        expected_fp = hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()[:32]
        
        self.assertEqual(fp, expected_fp)
        
        # Test it is deterministic (always same for same finding)
        self.assertEqual(_fingerprint(finding), fp)
