@echo off
setlocal

set "REPO_ROOT=%~dp0.."
set "SERVICE_DIR=%REPO_ROOT%\services\http-worker"
set "DOCKERFILE=%SERVICE_DIR%\Dockerfile"

docker build --target test -f "%DOCKERFILE%" --build-arg CONFIGURATION=Release "%SERVICE_DIR%"
exit /b %ERRORLEVEL%
