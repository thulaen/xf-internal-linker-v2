import importlib.util
import unittest
from pathlib import Path
import tempfile
import ast

_MOD_PATH = Path(__file__).resolve().parent / "check-no-duplicates-invariant.py"
_spec = importlib.util.spec_from_file_location("check_no_duplicates_invariant", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckNoDuplicatesInvariantTests(unittest.TestCase):
    def test_model_field_summary(self):
        source = """
migrations.CreateModel(
    name='MyModel',
    fields=[
        ('id', models.BigAutoField()),
        ('content_hash', models.CharField()),
        ('post', models.ForeignKey(to='app.Post')),
    ],
    options={
        'unique_together': {('content_hash', 'post')},
    },
)
        """
        tree = ast.parse(source)
        call = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'CreateModel':
                call = node
                break
                
        name, fields = mod.model_field_summary(call)
        self.assertEqual(name, 'MyModel')
        self.assertEqual(len(fields), 3)
        self.assertEqual(fields[1], ('content_hash', 'CharField'))

        targets = mod.fk_target_names(call)
        self.assertIn('Post', targets)

        self.assertTrue(mod.has_unique_constraint(call))

if __name__ == "__main__":
    unittest.main()
