@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or newer and try again.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    python -m venv .venv
    if errorlevel 1 goto error
)
echo Installing required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
if not exist ".env" (
    echo Creating local API keys...
    ".venv\Scripts\python.exe" -c "import secrets; open('.env','w',encoding='utf-8').write('ADMIN_KEY='+secrets.token_urlsafe(32)+'\nSENDER_KEY='+secrets.token_urlsafe(32)+'\n')"
    if errorlevel 1 goto error
)
echo.
echo Starting DakGhar at http://127.0.0.1:8000
echo Press CTRL+C to stop the server.
echo.
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
goto end
:error
echo.
echo Setup or startup failed. Check the message above.
pause
exit /b 1
:end
pause
