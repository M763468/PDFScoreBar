@echo off
rem PDFScoreBar Windows portable launcher (#535). Commands: setup, preflight, serve, run, review, verify.
rem The bundled interpreter runs isolated (-I); the launcher sets the child environment.
setlocal
"%~dp0python\python.exe" -I -X utf8 "%~dp0launcher\launcher.py" %*
exit /b %ERRORLEVEL%
