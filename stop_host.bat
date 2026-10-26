@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m deployment.host_control stop
pause
