@echo off
title J.A.R.V.I.S. - Desktop AI Assistant
cd /d "%~dp0"

echo ============================================================
echo   J.A.R.V.I.S.  -  Just A Rather Very Intelligent System
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi. Python 3.10+ yukleyin.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [KURULUM] .env olusturuluyor...
    copy ".env.example" ".env" >nul
    echo GEMINI_API_KEY girin ve tekrar calistirin:
    notepad ".env"
    pause
    exit /b 1
)

if not exist "venv\" (
    echo [KURULUM] Sanal ortam olusturuluyor...
    python -m venv venv
    echo [KURULUM] Paketler yukleniyor, bekleyin...
    venv\Scripts\pip install --upgrade pip -q
    venv\Scripts\pip install -r requirements.txt
)

call venv\Scripts\activate.bat
echo [BASLATILIYOR] J.A.R.V.I.S. ...
echo.
python main.py
if errorlevel 1 (
    echo.
    echo [HATA] Beklenmedik sekilde kapandi.
)
pause