@echo off
title RigelSLM Dashboard
cd /d %~dp0

echo ========================================
echo    RigelSLM Dashboard v3.0
echo ========================================
echo.

:: Verificar se o servidor está rodando
netstat -ano | findstr ":8000.*LISTENING" >nul
if %ERRORLEVEL% NEQ 0 (
    echo 🔧 Servidor nao encontrado. Iniciando...
    start /B python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000
    timeout /t 3 /nobreak >nul
) else (
    echo ✅ Servidor ja rodando
)

echo 🌐 Abrindo navegador...
setlocal enabledelayedexpansion

:: Tenta Chrome em locais comuns
for %%p in (
    "C:\Program Files\Google\Chrome\Application\chrome.exe"
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    "%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"
) do (
    if exist %%p (
        start "" %%p http://127.0.0.1:8000/
        goto :aberto
    )
)

:: Fallback: abre com o navegador padrão
start http://127.0.0.1:8000/

:aberto
echo.
echo 📊 Dashboard: http://127.0.0.1:8000
echo.
echo Para parar o servidor, feche esta janela
echo ou pressione Ctrl+C no terminal do servidor.
echo.
pause
