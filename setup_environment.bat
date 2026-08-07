@echo off
setlocal enabledelayedexpansion
title RigelSLM - Configuracao do ambiente
cd /d %~dp0

REM ================================================================
REM  setup_environment.bat - SUB-ROTINA de instalacao do RigelSLM
REM  Cria o .venv, instala dependencias, configura o .env e ajusta
REM  os limites de recursos a ESTA maquina (guardia de limites).
REM
REM  Chamado por: executemeprimeiro.bat e run_dashboard.bat
REM  Arquivo 100% ASCII (compativel com qualquer console Windows).
REM ================================================================

REM ----------------------------------------------------------------
REM  1) Python 3.11+
REM ----------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python NAO encontrado no PATH.
    echo         Baixe em: https://www.python.org/downloads/
    echo         IMPORTANTE: marque "Add Python to PATH" na instalacao.
    exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python instalado e ANTIGO - precisa 3.11 ou superior.
    echo         Baixe em: https://www.python.org/downloads/
    exit /b 1
)
python --version
echo  [OK] Python 3.11+ encontrado.

REM ----------------------------------------------------------------
REM  2) Ambiente virtual (.venv)
REM ----------------------------------------------------------------
if exist .venv\Scripts\activate.bat (
    echo  [OK] Ambiente virtual ja existe.
) else (
    echo  [..] Criando ambiente virtual - .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERRO] Falha ao criar o ambiente virtual.
        echo         Tente: python -m venv .venv  - e verifique o antivirus.
        exit /b 1
    )
    echo  [OK] Ambiente virtual criado.
)
call .venv\Scripts\activate.bat

REM ----------------------------------------------------------------
REM  3) Dependencias (requirements.txt) - com 1 retry automatico
REM ----------------------------------------------------------------
echo  [..] Instalando dependencias - requirements.txt...
echo        ATENCAO: isto pode demorar varios minutos - torch e grande.
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo  [AVISO] Falha na primeira tentativa. Tentando novamente...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo  [ERRO] Nao foi possivel instalar as dependencias.
        echo         Verifique a internet e rode de novo.
        exit /b 1
    )
)
echo  [OK] Dependencias instaladas.

REM ----------------------------------------------------------------
REM  4) Arquivo .env (a partir do template, sem sobrescrever)
REM ----------------------------------------------------------------
if exist .env (
    echo  [OK] Arquivo .env ja existe.
) else (
    if exist .env.template (
        copy .env.template .env >nul
        echo  [OK] Arquivo .env criado a partir do .env.template.
        echo       Edite DEEPSEEK_API_KEY depois, se quiser gerar pela API.
    ) else (
        echo  [AVISO] .env.template nao encontrado. Crie um .env manualmente.
    )
)

REM ----------------------------------------------------------------
REM  5) Limites de recursos PROPORCIONAIS a esta maquina
REM     (gera config_recursos.json - guardia de limites)
REM ----------------------------------------------------------------
echo  [..] Detectando hardware e ajustando limites de recursos...
python -m dashboard.services.recursos --salvar >nul 2>&1
if errorlevel 1 (
    echo  [AVISO] Nao foi possivel ajustar os limites - segue com padrao seguro.
) else (
    echo  [OK] Limites ajustados a esta maquina - config_recursos.json.
)

echo  [OK] Ambiente pronto.
exit /b 0
