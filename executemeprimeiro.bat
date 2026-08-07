@echo off
setlocal enabledelayedexpansion
title RigelSLM - Instalador (executemeprimeiro)
cd /d %~dp0
chcp 65001 >nul 2>&1

REM ================================================================
REM  executemeprimeiro.bat - INSTALADOR E INICIALIZADOR do RigelSLM
REM  Primeiro script a rodar depois de descompactar o pacote.
REM  Faz: ambiente + dependencias + Ollama + .env + dashboard.
REM  Arquivo 100% ASCII (compativel com qualquer console Windows).
REM ================================================================

echo ================================================================
echo  RIGELSLM - INSTALADOR E INICIALIZADOR
echo ================================================================
echo  Voce tem DUAS opcoes para gerar conteudo:
echo.
echo   1) API DeepSeek - recomendado p/ dados sinteticos de qualidade
echo      - Precisa de chave em: https://platform.deepseek.com/
echo      - Textos mais criativos e diversificados, mas tem custo
echo        por token.
echo.
echo   2) Somente Ollama local - sem custo
echo      - Ideal para testes e sem compartilhar dados.
echo      - Performance limitada pela CPU/GPU da sua maquina.
echo.
echo  Este script configura tudo e abre o dashboard no final.
echo ================================================================
echo.

REM ----------------------------------------------------------------
REM  1/3 - Ambiente (Python + .venv + dependencias + .env + limites)
REM ----------------------------------------------------------------
echo  [1/3] Configurando o ambiente - Python, .venv, dependencias...
call setup_environment.bat
if errorlevel 1 (
    echo.
    echo  [ERRO] Falha na configuracao do ambiente.
    echo         Resolva a mensagem acima e execute este script de novo.
    pause
    exit /b 1
)

REM ----------------------------------------------------------------
REM  2/3 - Ollama (opcional, nao bloqueia)
REM ----------------------------------------------------------------
echo  [2/3] Verificando Ollama...
call :verificar_ollama

REM ----------------------------------------------------------------
REM  3/3 - Iniciar o dashboard e abrir o navegador
REM ----------------------------------------------------------------
echo  [3/3] Iniciando o dashboard...
call :iniciar_dashboard

echo.
echo ================================================================
echo  INSTALACAO CONCLUIDA!
echo  - Para abrir de novo: de 2 cliques em run_dashboard.bat
echo  - Para gerar pela API: edite o .env - DEEPSEEK_API_KEY
echo  - Modelo local: instale o Ollama e baixe um modelo
echo ================================================================
pause
exit /b 0

REM ================================================================
REM  FUNCAO: verificar / instalar / baixar modelo do Ollama
REM ================================================================
:verificar_ollama
ollama --version >nul 2>&1
if not errorlevel 1 (
    echo  [OK] Ollama encontrado.
    set /p BAIXAR=  Baixar o modelo recomendado qwen2.5:7b agora? [S/N]:
    if /i "!BAIXAR!"=="S" (
        echo  [..] Baixando qwen2.5:7b - pode demorar...
        ollama pull qwen2.5:7b
        echo  [OK] Modelo baixado.
    )
    exit /b 0
)
echo  [..] Ollama NAO encontrado - opcional.
echo       Opcao 1: instale de https://ollama.com/download e rode de novo.
set /p INST=  Tentar instalar via winget agora? [S/N]:
if /i "!INST!"=="S" (
    winget install --id Ollama.Ollama -e >nul 2>&1
    if errorlevel 1 (
        echo  [AVISO] Falha no winget. Instale manualmente em:
        echo          https://ollama.com/download
    ) else (
        echo  [OK] Ollama instalado. Use o atalho do Menu Iniciar para iniciar.
    )
)
exit /b 0

REM ================================================================
REM  FUNCAO: iniciar o dashboard (sem --reload = estavel) e abrir o navegador
REM ================================================================
:iniciar_dashboard
start "RigelSLM Dashboard" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000"
echo  [..] Aguardando o servidor responder - ate ~40s...
set /a T=0
:espera
timeout /t 2 /nobreak >nul
curl.exe -s -o NUL -w "%%{http_code}" --max-time 3 http://127.0.0.1:8000/openapi.json > "%TEMP%\rigel_health.txt" 2>nul
set /p COD= < "%TEMP%\rigel_health.txt"
if "!COD!"=="200" (
    echo  [OK] Dashboard ativo em http://127.0.0.1:8000
    start "" "http://127.0.0.1:8000"
    exit /b 0
)
set /a T+=1
if !T! GEQ 20 (
    echo  [AVISO] Nao respondeu em 40s. Abrindo o navegador mesmo assim.
    start "" "http://127.0.0.1:8000"
    exit /b 0
)
goto :espera
