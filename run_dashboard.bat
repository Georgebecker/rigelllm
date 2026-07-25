@echo off
title RigelSLM Dashboard
cd /d %~dp0

:: Ativar virtualenv se existir
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

echo ========================================
echo  RigelSLM Dashboard v3.0
echo ========================================
echo 📊 http://127.0.0.1:8000
echo.
echo 🔧 Iniciando servidor (sem reload)...

:loop
python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000
echo.
echo ⚠️  Servidor caiu! Reiniciando em 3 segundos...
timeout /t 3 /nobreak >nul
goto loop