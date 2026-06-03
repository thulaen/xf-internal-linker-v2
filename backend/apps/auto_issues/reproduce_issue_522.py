import os
import django
from django.conf import settings

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.auto_issues.models import AutoIssue

print("Attempting to instantiate AutoIssue with abstract keyword argument...")
try:
    AutoIssue(abstract="This should fail")
    print("SUCCESS: AutoIssue instantiated with abstract (Wait, this shouldn't happen!)")
except TypeError as e:
    print(f"EXPECTED FAILURE: {e}")
except Exception as e:
    print(f"UNEXPECTED FAILURE: {type(e).__name__}: {e}")
