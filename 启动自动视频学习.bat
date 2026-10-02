@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
echo Please run the component installer first.
pause
exit /b 1
)
.venv\Scripts\python.exe server.py --port 8766 --open
pause
