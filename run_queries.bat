@echo off
echo Running search_resolved_issues for frontend/src/app/find-bugs...
docker compose exec -T backend python manage.py search_resolved_issues --area frontend/src/app/find-bugs

echo.
echo Running print_open_issues...
docker compose exec -T backend python manage.py print_open_issues

echo.
echo Querying specific AutoIssues #21231, #21233, #21235, #21238...
docker compose exec -T backend python manage.py shell < query_target_issues.py
pause
