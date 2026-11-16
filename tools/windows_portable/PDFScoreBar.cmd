@echo off
rem PDFScoreBar Windows portable launcher (#535). Commands: preflight, run, review, verify.
rem The bundled interpreter runs isolated (-I); the launcher sets the child environment.
setlocal
"%~dp0python\python.exe" -I -X utf8 "%~dp0app\tools\windows_portable\launcher.py" %*
exit /b %ERRORLEVEL%
