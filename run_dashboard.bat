@echo off
setlocal enabledelayedexpansion
title RigelSLM Dashboard (Auto-Recovery)
cd /d %~dp0

:: ============================================================================
::  CONFIGURACAO  (uso: run_dashboard.bat [porta]  - padrao: 8000)
::  Arquivo 100% ASCII (sem emojis/acentos) para funcionar em qualquer console.
:: ============================================================================
set "PORTA=8000"
if not "%1"=="" set "PORTA=%1"
set "URL=http://127.0.0.1:%PORTA%"
set "HEALTH=%URL%/openapi.json"

:: Ativar virtualenv se existir
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

echo ============================================================
echo  RigelSLM Dashboard v2.3.0 - Launcher Inteligente
echo ============================================================
echo  URL : %URL%
echo  Modo: auto-recuperacao + limpeza de porta + reload-dir
echo  (--reload-dir dashboard: nao vigia dados/ com milhoes de arqs)
echo  (navegador abre 1x por sessao; monitor unico)
echo.

set "NAVEGADOR_ABERTO=0"

:: ============================================================================
::  1) JA ESTA RODANDO? Nao derruba nada - so abre o navegador.
::     (Dica: abra apenas UMA janela do run_dashboard.bat por vez)
:: ============================================================================
call :check_server
if "!SERVER_OK!"=="1" (
    echo  [OK] Dashboard ja esta rodando em %URL%
    call :abrir_navegador
    echo  [i] Navegador aberto. Nada foi derrubado.
    goto Monitor
)

:: ============================================================================
::  GUARDA DE INSTANCIA UNICA: outra janela ja subiu o servidor e esta
::  cuidando dele -> nao duplica o monitor (evita abas/lutas pela porta).
:: ============================================================================
tasklist /FI "WINDOWTITLE eq RigelSLM Uvicorn" /FO CSV /NH 2>nul | findstr /i "cmd.exe" >nul
if not errorlevel 1 (
    echo  [!] Monitor duplicado detectado - janela RigelSLM Uvicorn ja existe.
    echo      Abrindo o navegador e encerrando este monitor extra.
    call :abrir_navegador
    exit /b 0
)

:: ============================================================================
::  2) LIMPEZA TOTAL da porta (qualquer estado) + uvicorns orfaos do projeto
:: ============================================================================
echo  [..] Limpando porta %PORTA% e processos orfaos...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":%PORTA% "') do (
    taskkill /F /T /PID %%a >nul 2>&1
)
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*dashboard.main*' } | ForEach-Object { $_.ProcessId }"`) do (
    taskkill /F /T /PID %%p >nul 2>&1
)
REM Tambem mata os workers orfaos do --reload (multiprocessing.spawn): eles
REM herdam o socket da porta e seguram o LISTEN mesmo com o pai morto,
REM travando o reinicio (taskkill no PID morto falha). Sem parenteses no PS.
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*spawn_main*' } | ForEach-Object { $_.ProcessId }"`) do (
    taskkill /F /T /PID %%p >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo  [OK] Porta %PORTA% limpa.

:: ============================================================================
::  3) INICIAR o servidor em janela propria (com --reload)
:: ============================================================================
:Start
echo [%time%] Iniciando Uvicorn (com --reload-dir dashboard)...
if exist .venv\Scripts\activate.bat (
    start "RigelSLM Uvicorn" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn dashboard.main:app --host 0.0.0.0 --port %PORTA% --reload --reload-dir dashboard --timeout-keep-alive 30"
) else (
    start "RigelSLM Uvicorn" /min cmd /c "python -m uvicorn dashboard.main:app --host 0.0.0.0 --port %PORTA% --reload --reload-dir dashboard --timeout-keep-alive 30"
)

:: Espera o servidor responder (ate ~60s no boot frio) antes do navegador
set /a TENTATIVA=0
:WaitHealthy
call :check_server
if "!SERVER_OK!"=="1" (
    echo  [OK] Servidor saudavel em %URL%
    call :abrir_navegador
    echo  [i] Navegador aberto. Dashboard ativo!
    goto Monitor
)
set /a TENTATIVA+=1
if !TENTATIVA! GEQ 60 (
    echo  [!] Servidor nao respondeu em 60s. Limpando e tentando de novo...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":%PORTA% "') do taskkill /F /T /PID %%a >nul 2>&1
    timeout /t 3 /nobreak >nul
    goto Start
)
timeout /t 1 /nobreak >nul
goto WaitHealthy

:: ============================================================================
::  4) MONITOR: auto-recuperacao (reinicia sozinho se cair)
:: ============================================================================
:Monitor
echo  [i] Monitorando o servidor (reinicia sozinho se cair)...
echo  (Feche esta janela para parar o monitoramento.)
:MonitorLoop
timeout /t 5 /nobreak >nul
call :check_server
if "!SERVER_OK!"=="1" goto MonitorLoop
echo [%time%] [!] Servidor caiu! Limpando e reiniciando...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":%PORTA% "') do taskkill /F /T /PID %%a >nul 2>&1
timeout /t 3 /nobreak >nul
goto Start

:: ============================================================================
::  FUNCAO: abre o navegador SOMENTE UMA VEZ por sessao do monitor.
::  (Cada chamada extra de start "" abria uma aba nova -> cascata de abas.)
:: ============================================================================
:abrir_navegador
if "!NAVEGADOR_ABERTO!"=="1" exit /b 0
start "" "%URL%"
set "NAVEGADOR_ABERTO=1"
exit /b 0

:: ============================================================================
::  FUNCAO: verifica se o servidor responde (HTTP 200 no openapi.json)
:: ============================================================================
:check_server
set "SERVER_OK=0"
for /f "delims=" %%c in ('curl.exe -s -o NUL -w "%%{http_code}" --max-time 5 "%HEALTH%" 2^>nul') do set "CODE=%%c"
if "!CODE!"=="200" set "SERVER_OK=1"
set "CODE="
exit /b