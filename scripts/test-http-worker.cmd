@echo off
setlocal

set "REPO_ROOT=%~dp0.."
powershell -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\test-http-worker.ps1" %*
exit /b %ERRORLEVEL%
