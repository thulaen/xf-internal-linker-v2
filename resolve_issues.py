from apps.auto_issues.models import AutoIssue
from django.utils import timezone

issue_ids = [21464, 21461, 21458, 21455, 21452, 21449]
issues = AutoIssue.objects.filter(id__in=issue_ids)

for issue in issues:
    # ensure we only prepend Trap/Fix shape once
    if "Trap:" not in issue.lessons_learned:
        if issue.id == 21461:
            trap = "Trap: Missing test case for run-lua-pretooluse-advisor.py."
            fix_shape = "Fix shape: Implemented test_run_lua_pretooluse_advisor.py to mock os.environ and assert _remote_docker_is_active and _remote_detail."
        elif issue.id == 21464:
            trap = "Trap: Lack of test coverage for run-multi-lang-observability-picker.py."
            fix_shape = "Fix shape: Existing test scripts/tests/test_run_multi_lang_observability_picker.py provides coverage using importlib to load script."
        elif issue.id == 21458:
            trap = "Trap: Quality cores script needs assurance of override behavior."
            fix_shape = "Fix shape: scripts/tests/test_quality_cores.py ensures XF_QUALITY_CORES parses correctly and override behavior holds."
        elif issue.id == 21455:
            trap = "Trap: Shard planner logic regressions on mint/windows."
            fix_shape = "Fix shape: scripts/tests/test_plan_scoped_quality_shards.py tests _cost and is_disposable_artifact."
        elif issue.id == 21452:
            trap = "Trap: mint_gc logic can delete referenced blobs."
            fix_shape = "Fix shape: test_mint_blob_store.py ensures referenced blobs are excluded from deletion."
        elif issue.id == 21449:
            trap = "Trap: mint_blob_store duplicate uploads could waste resources."
            fix_shape = "Fix shape: test_mint_blob_store.py verifies SCP and atomic move fire exactly once for duplicates."
        
        original_lesson = issue.lessons_learned or ""
        issue.lessons_learned = f"{trap} {fix_shape}\n\n{original_lesson}".strip()
    
    issue.status = 'resolved'
    issue.resolved_at = timezone.now()
    issue.save()

print("All 6 AutoIssues resolved successfully.")
