@echo off
title ContractsAI Launcher
color 0A

echo ===================================================
echo           ContractsAI Baslatiliyor...
echo ===================================================

:: 1. Check Dependencies
echo [1/4] Kutuphaneler kontrol ediliyor...
pip install -r requirements.txt > nul 2>&1
if %errorlevel% neq 0 (
    echo HATA: Python kutuphaneleri yuklenemedi. Lutfen Python ve pip'in kurulu oldugundan emin olun.
    pause
    exit /b
)

:: 2. Start Redis (Docker)
echo [2/4] Redis (Docker) kontrol ediliyor...
docker ps > nul 2>&1
if %errorlevel% neq 0 (
    echo HATA: Docker Desktop calismiyor! Lutfen Docker'i baslatin.
    pause
    exit /b
)

docker start contractsai-redis > nul 2>&1
if %errorlevel% neq 0 (
    echo Redis container olusturuluyor...
    docker run -d -p 6379:6379 --name contractsai-redis redis:alpine
)
echo Redis hazir.

:: 3. Start Celery Worker (New Window)
echo [3/4] Arka plan isleyici (Worker) baslatiliyor...
start "ContractsAI Worker (KAPATMAYIN)" cmd /k "cd src_python && celery -A celery_app worker --loglevel=info --pool=solo"

:: 4. Start Flower Monitoring (New Window - Minimized)
echo [4/4] Monitoring servisi baslatiliyor...
start "ContractsAI Monitor" /min cmd /k "cd src_python && celery -A celery_app flower --port=5555"

:: 5. Start Application
echo.
echo ===================================================
echo           TUM SISTEMLER HAZIR!
echo ===================================================
echo.
echo Uygulama baslatiliyor...
echo.
echo Arayuz: http://localhost:5173
echo API: http://localhost:8000
echo Monitor: http://localhost:5555
echo.

python run_dev.py

pause
