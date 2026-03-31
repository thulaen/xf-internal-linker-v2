@echo off
echo Cleaning up old tunnel processes...
taskkill /f /im cloudflared.exe >nul 2>&1
powershell -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*start_sync_tunnel*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
echo Done.
echo.

schtasks /create ^
  /tn "XF Linker Sync Tunnel" ^
  /tr "wscript.exe \"%~dp0tools\run_tunnel_hidden.vbs\"" ^
  /sc ONLOGON ^
  /ru "%USERNAME%" ^
  /f

if %errorlevel% == 0 (
    echo.
    echo SUCCESS: Tunnel watcher will now start automatically at every login.
    echo.
    echo Starting it now for this session...
    wscript.exe "%~dp0tools\run_tunnel_hidden.vbs"
    echo Done. The tunnel will come up within a few seconds.
) else (
    echo.
    echo FAILED to create the scheduled task. Try right-clicking this file and choosing "Run as administrator".
)
echo.
pause
