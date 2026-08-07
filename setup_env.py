#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup_env.py - Configuração automática do ambiente RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
Uso: python setup_env.py [--no-venv] [--no-cuda] [--install-extras]
"""
import os
import sys
import subprocess
import platform
import shutil
import argparse
import json
import time
from pathlib import Path
from datetime import datetime

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================
PROJETO_DIR = Path(__file__).resolve().parent
REQUIREMENTS = PROJETO_DIR / "requirements.txt"
ENV_EXAMPLE = PROJETO_DIR / ".env.example"
PASTAS_ESSENCIAIS = [
    "logs",
    "modelo",
    "tokenizer",
    "dados/raw",
    "dados/processed",
    "dados/gerados",
    "gguf",
    "dashboard/static",
    "dashboard/templates",
]

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def log(msg, emoji="📌", nivel="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{emoji} [{timestamp}] [{nivel}] {msg}")

def executar(cmd, descricao="Executando", shell=False, capture=True):
    """Executa um comando e retorna o código de saída."""
    log(f"{descricao}: {' '.join(cmd) if isinstance(cmd, list) else cmd}", emoji="⚙️")
    try:
        if shell:
            result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
        else:
            result = subprocess.run(cmd, capture_output=capture, text=True)
        if result.returncode != 0:
            if capture:
                log(f"❌ Erro: {result.stderr.strip()}", emoji="❌", nivel="ERRO")
            else:
                log(f"❌ Comando falhou com código {result.returncode}", emoji="❌", nivel="ERRO")
            return False
        if capture and result.stdout:
            log(result.stdout.strip(), emoji="📄", nivel="DEBUG")
        return True
    except Exception as e:
        log(f"❌ Exceção: {e}", emoji="❌", nivel="ERRO")
        return False

def verificar_ferramenta(nome, cmd=None):
    """Verifica se uma ferramenta está disponível no PATH."""
    if cmd is None:
        cmd = nome
    return shutil.which(cmd) is not None

def criar_pastas():
    """Cria as pastas essenciais do projeto."""
    for p in PASTAS_ESSENCIAIS:
        caminho = PROJETO_DIR / p
        caminho.mkdir(parents=True, exist_ok=True)
        log(f"Pasta verificada/criada: {caminho}", emoji="📁")

def verificar_python():
    """Verifica a versão do Python."""
    version = sys.version_info
    log(f"Python {version.major}.{version.minor}.{version.micro}", emoji="🐍")
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        log("Python 3.8 ou superior é necessário.", emoji="❌", nivel="ERRO")
        sys.exit(1)
    return True

def verificar_pip():
    """Verifica se o pip está disponível e atualizado."""
    if not verificar_ferramenta("pip"):
        log("pip não encontrado. Instale o pip.", emoji="❌", nivel="ERRO")
        return False
    log("pip encontrado.", emoji="✅")
    return True

def detectar_cuda():
    """Detecta se o PyTorch com CUDA está disponível."""
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        if cuda_avail:
            log(f"CUDA disponível: {torch.cuda.get_device_name(0)}", emoji="🚀")
        else:
            log("CUDA não disponível. Instalando PyTorch CPU.", emoji="💻")
        return cuda_avail
    except ImportError:
        log("PyTorch não instalado. Será instalado.", emoji="📦")
        return None

def instalar_pytorch(cuda_disponivel=None):
    """Instala o PyTorch com ou sem CUDA."""
    if cuda_disponivel is None:
        cuda_disponivel = detectar_cuda()
    if cuda_disponivel is None:
        # PyTorch não está instalado, vamos decidir
        if verificar_ferramenta("nvidia-smi"):
            cuda_disponivel = True
            log("NVIDIA GPU detectada via nvidia-smi.", emoji="🚀")
        else:
            cuda_disponivel = False
            log("Nenhuma GPU detectada. Instalando CPU.", emoji="💻")

    if cuda_disponivel:
        log("Instalando PyTorch com suporte CUDA...", emoji="📦")
        return executar(
            [sys.executable, "-m", "pip", "install", "torch", "torchvision", "torchaudio",
             "--index-url", "https://download.pytorch.org/whl/cu118"],
            "Instalando PyTorch CUDA"
        )
    else:
        log("Instalando PyTorch CPU...", emoji="📦")
        return executar(
            [sys.executable, "-m", "pip", "install", "torch", "torchvision", "torchaudio",
             "--index-url", "https://download.pytorch.org/whl/cpu"],
            "Instalando PyTorch CPU"
        )

def instalar_dependencias(extras=False):
    """Instala as dependências do requirements.txt."""
    if not REQUIREMENTS.exists():
        log("requirements.txt não encontrado.", emoji="❌", nivel="ERRO")
        return False
    log(f"Instalando dependências de {REQUIREMENTS}...", emoji="📦")
    if not executar([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
                    "Instalando dependências principais"):
        return False

    if extras:
        log("Instalando dependências extras (opcionais)...", emoji="📦")
        extras_list = ["hf_transfer", "sentencepiece", "protobuf"]
        for pkg in extras_list:
            executar([sys.executable, "-m", "pip", "install", pkg], f"Instalando {pkg}")
    return True

def criar_env_example():
    """Cria um arquivo .env.example se não existir."""
    if ENV_EXAMPLE.exists():
        log(".env.example já existe.", emoji="📄")
        return
    with open(ENV_EXAMPLE, "w", encoding="utf-8") as f:
        f.write("""# ============================================================================
# RIGELSLM - VARIÁVEIS DE AMBIENTE
# ============================================================================

# ----- API DeepSeek (para geração de dados) -----
DEEPSEEK_API_KEY=coloque_sua_chave_aqui
MODEL_NAME=deepseek-chat
MAX_COST_USD=5.00
DELAY_SECONDS=2.0

# ----- Ollama (modelos locais) -----
USE_OLLAMA=false
OLLAMA_URL=http://localhost:11434
# OLLAMA_MODELS=D:/LLMs/models   # Descomente para mudar o local dos modelos

# ----- Treino -----
# OMP_NUM_THREADS=16
# TORCH_NUM_THREADS=16

# ----- Guardião de limites (opcional; por padrão são PROPORCIONAIS ao
#      hardware, gravados em config_recursos.json na instalação). -----
# SCAN_MAX_ARQUIVOS=2000000
# SCAN_MAX_DIRETORIOS=200000
# SCAN_PAUSA_CADA=2000
# SCAN_PAUSA_SEG=0.002
# MEM_MIN_LIVRE_MB=1024
# MEM_MIN_LIVRE_PCT=12
# CPU_MAX_USO_PCT=75
# DISCO_MIN_LIVRE_PCT=5
# DISCO_MIN_LIVRE_MB=1024
# SCAN_MAX_NOMES_CACHE=2000
""")
    log(".env.example criado. Renomeie para .env e configure sua chave.", emoji="📄")

def verificar_ollama():
    """Verifica se o Ollama está instalado e sugere instalação."""
    if verificar_ferramenta("ollama"):
        log("Ollama encontrado.", emoji="✅")
        # Testa se o daemon está rodando
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if result.returncode == 0:
            log("Ollama está funcionando.", emoji="✅")
            # Exibe modelos disponíveis
            log("Modelos disponíveis:", emoji="📋")
            for line in result.stdout.strip().split('\n'):
                if line:
                    log(f"   {line}", emoji="🔹")
        else:
            log("Ollama não está rodando. Execute 'ollama serve' em outro terminal.", emoji="⚠️")
    else:
        log("Ollama não encontrado. Instale de https://ollama.com/", emoji="⚠️")

def verificar_espaco_disco():
    """Verifica o espaço em disco disponível (opcional)."""
    try:
        import shutil
        total, usado, livre = shutil.disk_usage(PROJETO_DIR)
        livre_gb = livre // (1024**3)
        log(f"Espaço disponível em {PROJETO_DIR}: {livre_gb} GB", emoji="💾")
        if livre_gb < 10:
            log("⚠️ Pouco espaço em disco. Considere liberar ou mover modelos.", emoji="⚠️")
    except:
        pass


def configurar_recursos():
    """Detecta o hardware desta máquina e grava limites PROPORCIONAIS em
    config_recursos.json (regra do usuário: cada máquina tem limites
    diferentes — RAM, CPU, GPU, HD/SSD/NVMe — definidos na instalação).
    Depois, cada limite pode ser ajustado no próprio arquivo ou via env."""
    # Garante que o pacote dashboard seja importável mesmo rodando fora dele
    if str(PROJETO_DIR) not in sys.path:
        sys.path.insert(0, str(PROJETO_DIR))
    try:
        from dashboard.services.recursos import (
            detectar_hardware, calcular_limites, salvar_limites, CONFIG_RECURSOS,
        )
    except Exception as e:
        log(f"Não foi possível carregar recursos.py: {e}", emoji="❌", nivel="ERRO")
        return
    log("Detectando hardware para limites proporcionais...", emoji="🖥️")
    hw = detectar_hardware()
    log(f"RAM {hw.get('ram_gb')} GB | {hw.get('cpu_cores')} cores | "
        f"disco {hw.get('disco_tipo')} ({hw.get('disco_livre_gb')} GB livres) | "
        f"GPU: {hw.get('gpu_nome') or 'não detectada'}", emoji="🛡️")
    lim = calcular_limites(hw)
    salvar_limites(lim, hw)
    log(f"Limites proporcionais gravados em {CONFIG_RECURSOS}:", emoji="📝")
    for k, v in lim.items():
        log(f"   {k} = {v}", emoji="🔹")
    log("Ajuste fino: edite config_recursos.json ou use variáveis de ambiente "
        "(ex.: MEM_MIN_LIVRE_PCT=15, SCAN_PAUSA_SEG=0.005).", emoji="💡")

def criar_scripts_auxiliares():
    """Cria scripts auxiliares para iniciar o Ollama e o dashboard."""
    # Script para iniciar Ollama (Windows)
    ollama_ps1 = PROJETO_DIR / "iniciar_ollama.ps1"
    if not ollama_ps1.exists():
        with open(ollama_ps1, "w", encoding="utf-8") as f:
            f.write("""# Iniciar Ollama com configuração otimizada
$env:OLLAMA_NUM_THREADS = "18"
$env:OLLAMA_MMAP = "true"
$env:OLLAMA_NUM_BATCH = "2048"
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
# Para mudar o local dos modelos, descomente e ajuste:
# $env:OLLAMA_MODELS = "D:/LLMs/models"
ollama serve
""")
        log("iniciar_ollama.ps1 criado.", emoji="📄")
    else:
        log("iniciar_ollama.ps1 já existe.", emoji="📄")

    # Script para iniciar o dashboard (Windows)
    dashboard_bat = PROJETO_DIR / "abrir_dashboard.bat"
    if not dashboard_bat.exists():
        with open(dashboard_bat, "w", encoding="utf-8") as f:
            f.write("""@echo off
title RigelSLM Dashboard
cd /d %~dp0
echo ========================================
echo    RigelSLM Dashboard v1.0.0
echo ========================================
echo.
:: Verifica se o servidor está rodando
netstat -ano | findstr ":8000.*LISTENING" >nul
if %ERRORLEVEL% NEQ 0 (
    echo 🔧 Servidor nao encontrado. Iniciando...
    start /B python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000
    timeout /t 3 /nobreak >nul
) else (
    echo ✅ Servidor ja rodando
)
echo 🌐 Abrindo navegador...
start http://127.0.0.1:8000/
echo.
echo 📊 Dashboard: http://127.0.0.1:8000
pause
""")
        log("abrir_dashboard.bat criado.", emoji="📄")
    else:
        log("abrir_dashboard.bat já existe.", emoji="📄")

def main():
    parser = argparse.ArgumentParser(description="Configuração automática do RigelSLM")
    parser.add_argument("--no-venv", action="store_true", help="Não verifica/ativa ambiente virtual")
    parser.add_argument("--no-cuda", action="store_true", help="Força instalação CPU mesmo com GPU")
    parser.add_argument("--install-extras", action="store_true", help="Instala pacotes extras (hf_transfer, etc.)")
    parser.add_argument("--skip-pytorch", action="store_true", help="Pula a instalação do PyTorch")
    args = parser.parse_args()

    log("🚀 INICIANDO CONFIGURAÇÃO DO AMBIENTE RIGELSLM", emoji="🌟")
    log(f"📂 Projeto em: {PROJETO_DIR}", emoji="📂")

    # 1. Verifica Python
    verificar_python()

    # 2. Verifica/ativa virtualenv (opcional)
    if not args.no_venv:
        if "VIRTUAL_ENV" not in os.environ:
            log("⚠️ Ambiente virtual não ativado. Recomendado.", emoji="⚠️")
            if PROJETO_DIR.joinpath(".venv").exists():
                log("   Ative com: .venv\\Scripts\\activate (Windows) ou source .venv/bin/activate (Linux)", emoji="💡")
            else:
                log("   Crie com: python -m venv .venv", emoji="💡")
        else:
            log(f"✅ Ambiente virtual ativo: {os.environ['VIRTUAL_ENV']}", emoji="✅")

    # 3. Cria pastas
    criar_pastas()

    # 4. Verifica pip
    if not verificar_pip():
        sys.exit(1)

    # 5. Instala PyTorch (se não pular)
    if not args.skip_pytorch:
        cuda_disponivel = None if args.no_cuda else detectar_cuda()
        if not instalar_pytorch(cuda_disponivel):
            log("Falha ao instalar PyTorch.", emoji="❌", nivel="ERRO")
            sys.exit(1)

    # 6. Instala dependências gerais
    if not instalar_dependencias(extras=args.install_extras):
        log("Falha ao instalar dependências.", emoji="❌", nivel="ERRO")
        sys.exit(1)

    # 7. Cria .env.example
    criar_env_example()

    # 8. Verifica Ollama
    verificar_ollama()

    # 9. Verifica espaço em disco
    verificar_espaco_disco()

    # 9.5 Limites PROPORCIONAIS ao hardware (guardião) — regra do usuário
    configurar_recursos()

    # 10. Cria scripts auxiliares
    criar_scripts_auxiliares()

    # 11. Verifica dependências específicas (ex: datasets, tokenizers)
    log("Verificando instalação de pacotes críticos...", emoji="🔍")
    pacotes = ["torch", "tokenizers", "transformers", "fastapi", "uvicorn", "datasets", "gguf"]
    for pkg in pacotes:
        try:
            __import__(pkg)
            log(f"   ✅ {pkg}", emoji="✅")
        except ImportError:
            log(f"   ❌ {pkg} não encontrado", emoji="❌")

    log("✅ AMBIENTE CONFIGURADO COM SUCESSO!", emoji="🎉")
    log("💡 Agora execute: python rigel.py", emoji="💡")
    log("📄 Consulte .env.example para configurar sua chave da DeepSeek.", emoji="📄")

if __name__ == "__main__":
    main()