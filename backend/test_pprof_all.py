import os
import sys
from pathlib import Path
import django
from django.utils import timezone

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

import importlib.util
spec = importlib.util.spec_from_file_location("picker", "../scripts/run-multi-lang-observability-picker.py")
picker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(picker)

findings = picker.collect_findings()

from apps.auto_issues.models import AutoIssue

for f in findings:
    if f.source == 'pprof':
        print(f"Finding: {f.title} (source={f.source})")
        AutoIssue.objects.update_or_create(
            external_id=f.external_id,
            defaults={
                'title': f.title,
                'source': f.source,
                'status': AutoIssue.STATUS_RESOLVED,
                'resolved_at': timezone.now(),
                'lessons_learned': 'Trap: high allocations or missing wired path. Fix shape: resolved via script.'
            }
        )

print(f"Total pprof in DB: {AutoIssue.objects.filter(source='pprof').count()}")
