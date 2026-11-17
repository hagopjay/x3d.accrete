@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import lxml, jsonschema" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe serve.py --open
if errorlevel 1 goto failed
exit /b 0
:failed
echo Setup or server startup failed. Read the message above; Python 3.12+ is required.
pause
exit /b 1
