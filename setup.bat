@echo off
title RigelSLM - Setup Automático
chcp 65001 >nul

echo ============================================================
echo    ⭐ RIGELSLM - SETUP AUTOMÁTICO (Windows)
echo ============================================================
echo.

REM ─── 1. Verificar Python ───
echo [1/6] 🔍 Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo    ⚠️ Python 3.10+ não encontrado.
    echo    Deseja baixar e instalar automaticamente? (S/N)
    set /p resp="   👉 "
    if /i "!resp!"=="S" (
        echo    📥 Baixando Python 3.12...
        curl -o python_installer.exe https://www.python.org/ftp/python/3.12.5/python-3.12.5-amd64.exe
        echo    🔧 Instalando Python (marque "Add Python to PATH")...
        start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
        del python_installer.exe
    ) else (
        echo    ❌ Python é necessário. Instale manualmente em: https://www.python.org/downloads/
        pause
        exit /b 1
    )
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo    ✅ Python %%v encontrado
)

REM ─── 1.5 Guardião de cabeçalhos (oculto + criptografado) ───
python .rigel_guard.py >nul 2>&1

REM ─── 2. Criar ambiente virtual ───
echo [2/6] 🔧 Criando ambiente virtual...
if exist .venv (
    echo    ✅ Ambiente virtual já existe.
) else (
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo    ❌ Erro ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo    ✅ Ambiente virtual criado em .venv/
)

REM ─── 3. Ativar venv e instalar dependências ───
echo [3/6] 📦 Instalando dependências...
call .venv\Scripts\activate.bat
if exist requirements.txt (
    pip install --upgrade pip -q
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo    ⚠️ Algumas dependências podem não ter sido instaladas.
    ) else (
        echo    ✅ Dependências instaladas com sucesso.
    )
) else (
    echo    ⚠️ requirements.txt não encontrado. Pulando...
)

REM ─── 4. Criar pastas necessárias ───
echo [4/6] 📁 Criando estrutura de pastas...
for %%p in (dados modelo logs estado gguf) do (
    if not exist %%p (
        mkdir %%p
        echo    ✅ Pasta '%%p' criada.
    ) else (
        echo    ✅ Pasta '%%p' já existe.
    )
)

REM ─── 5. Configurar .env ───
echo [5/6] 🔑 Configurando variáveis de ambiente...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo    ⚠️ Arquivo .env criado a partir de .env.example.
        echo    Edite o arquivo .env para adicionar sua chave DeepSeek.
    ) else (
        echo    🔑 Criando .env básico...
        (
            echo # DeepSeek API
            echo DEEPSEEK_API_KEY=deepseek-aqui
            echo.
            echo # Caminhos
            echo PROJETO_DIR=%CD%
        ) > .env
        echo    ✅ .env criado com valores padrão.
    )
) else (
    echo    ✅ .env já existe.
)

REM ─── 5.5 Limites proporcionais ao hardware (guardião) ───
echo [5.5/6] 🖥️ Detectando hardware e gravando limites proporcionais...
python -m dashboard.services.recursos --salvar
if %errorlevel% neq 0 (
    echo    ⚠️ Não foi possível detectar o hardware automaticamente.
    echo    O guardião usará limites padrão seguros.
)

REM ─── 6. Verificar/Instalar Ollama ───
echo [6/6] 🦙 Verificando Ollama...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo    ⚠️ Ollama não encontrado.
    echo    Deseja instalar o Ollama? (S/N)
    set /p resp="   👉 "
    if /i "!resp!"=="S" (
        echo    📥 Baixando Ollama...
        curl -o ollama_setup.exe https://ollama.com/download/OllamaSetup.exe
        echo    🔧 Instalando...
        start /wait ollama_setup.exe /silent
        del ollama_setup.exe
        echo    ✅ Ollama instalado. Inicie com: ollama serve
    )
) else (
    for /f "tokens=3" %%v in ('ollama --version') do echo    ✅ Ollama %%v encontrado
)

echo.
echo ============================================================
echo    ✅ SETUP CONCLUÍDO!
echo ============================================================
echo.
echo    📌 Próximos passos:
echo    1. Ative o ambiente: .venv\Scripts\activate
echo    2. Edite o .env com sua chave DeepSeek
echo    3. Execute: python verificador.py
echo    4. Para iniciar: python rigel.py
echo.
pause
