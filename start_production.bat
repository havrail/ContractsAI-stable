@echo off
REM ContractsAI - Production Mode Launcher
REM No auto-reload, stable operation

echo ============================================
echo ContractsAI - PRODUCTION MODE
echo ============================================
echo.

REM Check if Celery is running
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [WARNING] Python processes already running
    echo Press CTRL+C to cancel, or
    pause
)

echo [1/3] Starting Celery Worker...
start "Celery Worker" cmd /k "cd src_python && celery -A celery_app worker --loglevel=info --pool=solo"

timeout /t 3 /nobreak >nul

echo [2/3] Starting Backend (Production Mode)...
echo.
python run_prod.py

pause
