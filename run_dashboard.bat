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

:: IP da rede local (cabo/wifi) para abrir o navegador - se detectado,
:: abre no IP da rede (ex.: 192.168.3.150) em vez de 127.0.0.1 (acessivel
:: por celular/TV na mesma rede). O healthcheck continua em 127.0.0.1.
set "URL_PUBLICA=%URL%"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1).IPAddress"`) do (
    if not "%%i"=="" set "URL_PUBLICA=http://%%i:%PORTA%"
)

:: Ativar virtualenv se existir
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

echo ============================================================
echo  RigelSLM Dashboard v2.3.0 - Launcher Inteligente
echo ============================================================
echo  URL : %URL%
echo  URL publica (rede): %URL_PUBLICA%
echo  Modo: auto-recuperacao + limpeza de porta + reload-dir
echo  (--reload-dir dashboard: nao vigia dados/ com milhoes de arqs)
echo  (navegador abre 1x por sessao; monitor unico)
echo  (timeout 30s: processamento pesado NAO derruba o servidor)
echo  (REGRA DE OURO: se cair, levantar - auto-recuperacao + limpeza de orfaos)
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
::  2) LIMPEZA da porta + uvicorns orfaos do projeto.
::  IMPORTANTE (regra 13/08): NAO usa /T (arvore). O taskkill /T mataria
::  TAMBEM os filhos do EXECUTOR (ex.: limpeza do dolphin) que estao sendo
::  gerenciados pelo dashboard. Aqui matamos SOMENTE o que escuta a porta e
::  os processos do proprio uvicorn - os subprocessos do executor (limpeza,
::  treino, etc.) seguem vivos e sao reancorados apos o reload.
:: ============================================================================
call :limpar_porta

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
::  Timeout 30s: processamento pesado (langdetect/limpeza/treino) pode deixar
::  o servidor lento por alguns segundos - isso NAO e queda. So reinicia
::  se ficar 30s sem responder (e ainda assim preserva os filhos do executor).
:: ============================================================================
:Monitor
echo  [i] Monitorando o servidor (reinicia sozinho se cair - timeout 30s)...
echo  (Feche esta janela para parar o monitoramento.)
:MonitorLoop
timeout /t 10 /nobreak >nul
call :check_server
if "!SERVER_OK!"=="1" goto MonitorLoop
echo [%time%] [!] Servidor nao respondeu em 30s! Auto-recuperando (regra de ouro)...
call :limpar_porta
goto Start

:: ============================================================================
::  FUNCAO: abre o navegador SOMENTE UMA VEZ por sessao do monitor.
::  (Cada chamada extra de start "" abria uma aba nova -> cascata de abas.)
:: ============================================================================
:abrir_navegador
if "!NAVEGADOR_ABERTO!"=="1" exit /b 0
start "" "%URL_PUBLICA%"
set "NAVEGADOR_ABERTO=1"
exit /b 0

:: ============================================================================
::  FUNCAO: verifica se o servidor responde (HTTP 200 no openapi.json)
:: ============================================================================
:check_server
set "SERVER_OK=0"
for /f "delims=" %%c in ('curl.exe -s -o NUL -w "%%{http_code}" --max-time 30 "%HEALTH%" 2^>nul') do set "CODE=%%c"
if "!CODE!"=="200" set "SERVER_OK=1"
set "CODE="
exit /b

:: ============================================================================
::  FUNCAO: limpeza ROBUSTA da porta (regra de ouro 14/08/2026).
::  Alem de matar os processos, ESPERA a porta LIBERAR de verdade (bind test).
::  Workers orfaos do uvicorn --reload (multiprocessing.spawn_main) herdam o
::  socket LISTEN da porta e o seguram mesmo com o pai morto: qualquer
;;  reinicio sem isso vira sobe-morre em loop. Aqui: mata -> espera bind livre
;;  -> se ainda presa, limpeza extra via PowerShell e diagnostico do guardiao.
;; ============================================================================
:limpar_porta
echo  [..] Limpando porta %PORTA% (sem matar filhos do executor)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:":%PORTA% "') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*dashboard.main*' } | ForEach-Object { $_.ProcessId }"`) do (
    taskkill /F /PID %%p >nul 2>&1
)
REM Workers orfaos do --reload (multiprocessing.spawn) herdam o socket da porta
REM e seguram o LISTEN mesmo com o pai morto -> travam o reinicio. Matar.
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*spawn_main*' } | ForEach-Object { $_.ProcessId }"`) do (
    taskkill /F /PID %%p >nul 2>&1
)
REM Espera a porta LIBERAR de verdade (bind test) - ate 30s.
set /a TENT=0
:limpar_espera
if !TENT! GEQ 6 goto limpar_verdict
powershell -NoProfile -Command "try { $s=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Any,%PORTA%); $s.Start(); $s.Stop(); exit 0 } catch { exit 1 }" >nul 2>&1
if !errorlevel! EQU 0 goto limpar_ok
set /a TENT+=1
timeout /t 5 /nobreak >nul
goto limpar_espera
:limpar_verdict
echo  [!] Porta %PORTA% ainda presa apos limpeza (socket orfao). Limpeza extra...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -match 'spawn_main|dashboard\.main|uvicorn') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 5 /nobreak >nul
powershell -NoProfile -Command "try { $s=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Any,%PORTA%); $s.Start(); $s.Stop(); exit 0 } catch { exit 1 }" >nul 2>&1
if !errorlevel! EQU 0 goto limpar_ok
echo  [!!!] Porta %PORTA% continua presa. Consulte logs/saude.log (guardiao). [!!!]
:limpar_ok
echo  [OK] Porta %PORTA% limpa (filhos do executor preservados).
exit /b 0