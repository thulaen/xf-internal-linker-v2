import importlib.util
import sys
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-design-patterns.py"
_spec = importlib.util.spec_from_file_location("check_design_patterns", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
# Register before exec so the module's @dataclass can resolve its own
# __module__ via sys.modules (Python 3.12 dataclasses requirement).
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

class CheckDesignPatternsTests(unittest.TestCase):
    def test_is_exempt(self):
        self.assertTrue(mod._is_exempt(Path("frontend/src/app/error-log/foo.html")))
        self.assertFalse(mod._is_exempt(Path("frontend/src/app/settings/foo.html")))

    def test_legacy_status_toggle_regex(self):
        source = """
        <mat-form-field>
          <mat-label>Status</mat-label>
          <mat-select>
            <mat-option [value]="true">Active</mat-option>
            <mat-option [value]="false">Off</mat-option>
          </mat-select>
        </mat-form-field>
        """
        match = mod.LEGACY_STATUS_TOGGLE_RE.search(source)
        self.assertIsNotNone(match)

    def test_legacy_status_toggle_regex_no_match(self):
        # A legitimate filter with other states
        source = """
        <mat-form-field>
          <mat-label>Status</mat-label>
          <mat-select>
            <mat-option value="Pending">Pending</mat-option>
            <mat-option value="Approved">Approved</mat-option>
          </mat-select>
        </mat-form-field>
        """
        match = mod.LEGACY_STATUS_TOGGLE_RE.search(source)
        self.assertIsNone(match)

if __name__ == "__main__":
    unittest.main()
