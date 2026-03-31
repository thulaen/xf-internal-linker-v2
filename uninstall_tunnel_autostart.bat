@echo off
schtasks /delete /tn "XF Linker Sync Tunnel" /f
echo Tunnel autostart removed.
pause
