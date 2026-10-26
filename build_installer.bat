@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" build_release.py --installer
if errorlevel 1 goto :failed
echo Installer created in dist\installer.
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
