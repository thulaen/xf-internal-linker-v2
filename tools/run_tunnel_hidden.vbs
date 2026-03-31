Dim shell, scriptDir
Set shell = CreateObject("WScript.Shell")
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
scriptDir = Left(scriptDir, InStrRev(scriptDir, "\"))
shell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -NonInteractive -File """ & scriptDir & "start_sync_tunnel.ps1""", 0, False
Set shell = Nothing
