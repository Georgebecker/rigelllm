#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
deploy_package.py - Empacotador do RigelSLM para distribuicao.

Gera um ZIP pronto para rodar em outra maquina (Windows/Linux):
    python deploy_package.py [--dest PASTA] [--sem-checkpoints] [--dry-run]

SEGURANCA / REGRAS:
  - NAO modifica nenhum arquivo existente do projeto (somente leitura).
  - Cria apenas: o ZIP de saida em <dest>/rigelslm_dist.zip e uma pasta
    temporaria interna (apagada ao final).
  - Nunca copia: dados/, logs/, gguf/, .env, caches, backups, checkpoints
    de epoca, configuracoes de hardware (config_recursos.json e regerado
    na maquina de destino pelo instalador).

FLUXO:
  1. Monta o "plano" do que entra no pacote (auditavel com --dry-run).
  2. Copia para uma pasta temporaria (estrutura do pacote).
  3. Gera os scripts do pacote: run_dashboard.bat, setup.sh, run_dashboard.sh,
     MANIFESTO.txt.
  4. Compacta tudo em <dest>/rigelslm_dist.zip.
  5. Mostra o resumo (arquivos, tamanho, destino).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Log persistente do empacotamento (rastro para diagnostico de problemas)
LOG_DEPLOY = RAIZ / "logs" / "deploy.log"


def _log(msg: str, console: bool = True) -> None:
    """Imprime na tela (info) e registra em logs/deploy.log (rastro)."""
    try:
        LOG_DEPLOY.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_DEPLOY, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except Exception:
        pass
    if console:
        print(msg)

# ============================================================================
# CONFIGURACAO DO PACOTE
# ============================================================================
NOME_ZIP = "rigelslm_dist.zip"

# Pastas copiadas por inteiro (com exclusoes internas)
PASTAS_COMPLETAS = ["dashboard", "tokenizer", "docs", "scripts", "skills", "images"]

# Exclusoes GLOBAIS (aplicadas a qualquer copia recursiva)
EXCLUIR_DIRS = {"__pycache__", ".pytest_cache", ".git", ".venv", "node_modules",
                ".cache", ".github", "dist", "build", "backups", "jsonlogs"}
EXCLUIR_SUFIXOS = (".pyc", ".pyo", ".bak", ".backup", ".log", ".tmp")
EXCLUIR_PREFIXOS = ("checkpoint_ep", ".tmp", "comando_", "STOP_TREINO")

# Arquivos raiz que NAO entram (por nome)
EXCLUIR_ARQUIVOS_RAIZ = {
    "deploy_package.py",             # ferramenta de dev (nao vai no pacote)
    "converter_para_gguf_old.py",    # versao antiga do conversor
    "requirements_old.txt",          # requirements antigos
    "config_recursos.json",          # especifico da maquina (regerado no destino)
    "organizar_status.json",         # status orfao
    "registro_pastas.json",          # registro interno
    "processados.txt",               # lista de hashes interna
    "desktop.ini",                   # arquivo do Windows
    "package.json",                  # ferramenta de dev
    "settings.json",                 # config do VS Code
    "agent.md",                      # config do agente (dev)
    ".rigel_guard.py",               # guarda de cabecalho (dev)
    "checkpoint.json",               # resume do createjsonl (fica no original)
}

# Arquivos nao-.py da raiz que DEVEM entrar no pacote
ARQUIVOS_RAIZ_EXTRA = [
    "requirements.txt",
    "feeds.txt",
    "topicos.txt",
    "blacklist.txt",
    "knowledge_base.json",
    "estado_global.json",
    "RigelSLM_Colab.ipynb",
    "iniciar_ollama.ps1",
    "README.md",
    "INSTALL.md",
    ".env.template",
    "executemeprimeiro.bat",
    "setup_environment.bat",
    "setup.bat",
    "README_instalacao.txt",
]

# Arquivos do modelo que entram (obrigatorios) + checkpoints OPCIONAIS
MODELO_INCLUIR = ["modelo.pt", "modelo_melhor.pt", "tokenizer.json",
                  "estado_treino.json", "estado_treino_jsonl.json"]
MODELO_CHECKPOINTS = ["checkpoint.pt", "checkpoint_jsonl.pt"]

# Pastas VAZIAS criadas no pacote (estrutura)
PASTAS_VAZIAS = ["dados/raw", "dados/processed", "dados/gerados", "dados/descartados",
                 "logs", "gguf"]


# ============================================================================
# SCRIPTS GERADOS PARA DENTRO DO PACOTE
# (o projeto ja tem run_dashboard.bat e setup.sh proprios - estes sao as
#  versoes SIMPLES e auto-contidas do pacote, geradas aqui)
# ============================================================================

RUN_DASHBOARD_BAT = r'''@echo off
setlocal enabledelayedexpansion
title RigelSLM Dashboard
cd /d %~dp0

REM ================================================================
REM  run_dashboard.bat - abre o dashboard do RigelSLM
REM  (criado automaticamente pelo deploy_package.py)
REM ================================================================

if not exist .venv\Scripts\activate.bat (
    echo  [ERRO] Ambiente nao configurado.
    echo         Rode executemeprimeiro.bat primeiro.
    pause
    exit /b 1
)

echo  [..] Iniciando o dashboard em http://127.0.0.1:8000 ...
start "RigelSLM Dashboard" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000"

set /a T=0
:espera
timeout /t 2 /nobreak >nul
curl.exe -s -o NUL -w "%%{http_code}" --max-time 3 http://127.0.0.1:8000/openapi.json > "%TEMP%\rigel_health.txt" 2>nul
set /p COD= < "%TEMP%\rigel_health.txt"
if "!COD!"=="200" (
    start "" "http://127.0.0.1:8000"
    echo  [OK] Dashboard ativo.
    exit /b 0
)
set /a T+=1
if !T! GEQ 20 (
    echo  [AVISO] Nao respondeu em 40s. Abrindo o navegador mesmo assim.
    start "" "http://127.0.0.1:8000"
    exit /b 0
)
goto :espera
'''

SETUP_SH = r'''#!/bin/bash
# ============================================================
#  RigelSLM - Instalador Linux/macOS (gerado pelo deploy)
# ============================================================
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo " RIGELSLM - INSTALADOR (Linux/macOS)"
echo "============================================================"
echo " Duas opcoes de geracao de conteudo:"
echo "  1) API DeepSeek  -> qualidade alta, custo por token"
echo "  2) Ollama local  -> sem custo, qualidade depende do modelo"
echo

# 1) Python 3.11+
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[ERRO] Python 3.11+ nao encontrado."
    echo "       Ubuntu: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
$PY -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" || {
    echo "[ERRO] Python antigo (precisa 3.11+)."
    exit 1
}
echo "[OK] $($PY --version)"

# 2) venv + dependencias
if [ ! -d ".venv" ]; then
    echo "[..] Criando .venv..."
    $PY -m venv .venv
fi
source .venv/bin/activate
echo "[..] Instalando dependencias (pode demorar - torch e grande)..."
pip install --upgrade pip -q
pip install -r requirements.txt || pip install -r requirements.txt
echo "[OK] Dependencias instaladas."

# 3) Limites proporcionais ao hardware desta maquina
echo "[..] Ajustando limites de recursos..."
python -m dashboard.services.recursos --salvar >/dev/null 2>&1 || true
echo "[OK] Limites ajustados (config_recursos.json)."

# 4) Arquivo .env
if [ ! -f ".env" ]; then
    if cp .env.template .env 2>/dev/null; then
        echo "[OK] .env criado (edite DEEPSEEK_API_KEY se quiser a API)."
    else
        echo "[AVISO] Sem .env.template - crie um .env manualmente."
    fi
fi

# 5) Ollama (opcional, nao bloqueia)
if command -v ollama >/dev/null 2>&1; then
    echo "[OK] Ollama encontrado."
    read -r -p "Baixar o modelo qwen2.5:7b agora? (s/N): " BAIXAR
    if [ "$BAIXAR" = "s" ] || [ "$BAIXAR" = "S" ]; then
        ollama pull qwen2.5:7b
    fi
else
    echo "[..] Ollama nao encontrado (opcional). Instale: https://ollama.com/download"
fi

# 6) Iniciar o dashboard
echo "[..] Iniciando o dashboard..."
mkdir -p logs
nohup python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000 > logs/uvicorn.log 2>&1 &
sleep 4
echo "[OK] Dashboard em http://127.0.0.1:8000"
xdg-open "http://127.0.0.1:8000" 2>/dev/null || open "http://127.0.0.1:8000" 2>/dev/null || true
echo "Para abrir depois: ./run_dashboard.sh"
'''

RUN_DASHBOARD_SH = r'''#!/bin/bash
# Abre o dashboard do RigelSLM (gerado pelo deploy)
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "[ERRO] Rode ./setup.sh primeiro."
    exit 1
fi
source .venv/bin/activate
mkdir -p logs
nohup python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000 > logs/uvicorn.log 2>&1 &
sleep 4
xdg-open "http://127.0.0.1:8000" 2>/dev/null || open "http://127.0.0.1:8000" 2>/dev/null || true
echo "Dashboard em http://127.0.0.1:8000"
'''


# ============================================================================
# PLANEJAMENTO (auditavel) e MONTAGEM
# ============================================================================

def _eh_backup(nome: str) -> bool:
    """True para qualquer arquivo de backup (nome contem '.bak', ex.:
    main.py.bak_pre_datasets, dialogos2.py.bak, x.bak2026)."""
    return ".bak" in nome.lower()


def _copiar_recursivo(origem: Path, prefixo_rel: str):
    """Gera (origem, relativo) de todos os arquivos de uma arvore, com exclusoes."""
    for raiz, dirs, arquivos in os.walk(origem):
        dirs[:] = [d for d in dirs if d not in EXCLUIR_DIRS]
        for nome in arquivos:
            if (nome.endswith(EXCLUIR_SUFIXOS) or nome.startswith(EXCLUIR_PREFIXOS)
                    or _eh_backup(nome)):
                continue
            p = Path(raiz) / nome
            rel = (Path(prefixo_rel) / p.relative_to(origem)).as_posix()
            yield p, rel


def listar_conteudo(incluir_checkpoints: bool) -> list[tuple[Path, str]]:
    """Retorna [(origem_absoluta, destino_relativo)] de tudo que entrara no ZIP."""
    arquivos: list[tuple[Path, str]] = []

    # --- Raiz: scripts .py essenciais + extras ---
    for item in sorted(RAIZ.iterdir()):
        nome = item.name
        if item.is_file():
            if nome.endswith(".py"):
                if (nome in EXCLUIR_ARQUIVOS_RAIZ
                        or nome.endswith(EXCLUIR_SUFIXOS)
                        or _eh_backup(nome)):
                    continue
                arquivos.append((item, nome))
            elif nome in ARQUIVOS_RAIZ_EXTRA:
                arquivos.append((item, nome))
        elif item.is_dir() and nome in PASTAS_COMPLETAS:
            arquivos.extend(_copiar_recursivo(item, nome))

    # --- Modelo (somente arquivos selecionados; checkpoints opcionais) ---
    modelo_dir = RAIZ / "modelo"
    for nome in MODELO_INCLUIR:
        p = modelo_dir / nome
        if p.exists():
            arquivos.append((p, f"modelo/{nome}"))
    if incluir_checkpoints:
        for nome in MODELO_CHECKPOINTS:
            p = modelo_dir / nome
            if p.exists():
                arquivos.append((p, f"modelo/{nome}"))

    return arquivos


def montar_pacote(arquivos: list[tuple[Path, str]], pasta_tmp: Path,
                  quiet: bool = False) -> None:
    """Copia o plano + gera os scripts do pacote na pasta temporaria."""
    # Pastas vazias (estrutura)
    for rel in PASTAS_VAZIAS:
        (pasta_tmp / rel).mkdir(parents=True, exist_ok=True)

    # Arquivos reais (com progresso informativo a cada 50)
    total = max(1, len(arquivos))
    for n, (src, rel) in enumerate(arquivos, start=1):
        dest = pasta_tmp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if not quiet and n % 50 == 0:
            _log(f"  copiando {n}/{total} arquivos...")
    if not quiet:
        _log(f"  copiados {len(arquivos)}/{total} arquivos.")

    # Scripts gerados
    (pasta_tmp / "run_dashboard.bat").write_text(RUN_DASHBOARD_BAT, encoding="utf-8")
    (pasta_tmp / "setup.sh").write_text(SETUP_SH, encoding="utf-8")
    (pasta_tmp / "run_dashboard.sh").write_text(RUN_DASHBOARD_SH, encoding="utf-8")

    # Manifesto
    gerar_manifesto(pasta_tmp, arquivos)


def gerar_manifesto(pasta_tmp: Path, arquivos: list[tuple[Path, str]]) -> None:
    linhas = [
        "RIGELSLM - PACOTE DE DISTRIBUICAO",
        f"Gerado em: {datetime.now().isoformat()}",
        f"Python usado: {sys.version.split()[0]}",
        f"Total de arquivos: {len(arquivos)}",
        "",
        "O QUE ESTA DENTRO:",
        "  - dashboard/ (FastAPI completo)",
        "  - modelo/ (pesos .pt + estado de treino)",
        "  - tokenizer/",
        "  - scripts Python essenciais (treino, chat, conversor, geradores...)",
        "  - requirements.txt, .env.template, instaladores",
        "",
        "O QUE NAO ENTROU (por seguranca/limpeza):",
        "  - dados/, logs/, gguf/ (criadas vazias)",
        "  - .env (criado na instalacao a partir do .env.template)",
        "  - caches (__pycache__), .pyc, backups, .bak, logs antigos",
        "  - config_recursos.json (regerado na maquina de destino)",
        "  - checkpoints de epoca (checkpoint_ep*)",
        "",
        "COMO INSTALAR:",
        "  - Windows: executemeprimeiro.bat",
        "  - Linux:   ./setup.sh",
    ]
    (pasta_tmp / "MANIFESTO.txt").write_text("\n".join(linhas), encoding="utf-8")


# ============================================================================
# ZIP
# ============================================================================

def criar_zip(pasta_tmp: Path, zip_path: Path, quiet: bool = False) -> int:
    """Compacta a pasta temporaria. Retorna o total de arquivos."""
    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for arquivo in sorted(pasta_tmp.rglob("*")):
            if not arquivo.is_file():
                continue
            rel = arquivo.relative_to(pasta_tmp).as_posix()
            z.write(arquivo, rel)
            # Marca .sh como executavel (preserva permissao no Linux)
            if arquivo.suffix == ".sh":
                info = z.getinfo(rel)
                info.external_attr = 0o755 << 16
            total += 1
            if not quiet and total % 300 == 0:
                _log(f"    ... {total} arquivos compactados")
    return total


# ============================================================================
# INTERFACE
# ============================================================================

def _perguntar(texto: str, padrao: str = "") -> str:
    try:
        return input(texto).strip()
    except (EOFError, KeyboardInterrupt):
        return padrao


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Empacota o RigelSLM em um ZIP distribuivel.")
    parser.add_argument("--dest", help="Pasta de saida do ZIP (ex.: D:\\dist)")
    parser.add_argument("--sem-checkpoints", action="store_true",
                        help="Nao incluir checkpoint.pt/checkpoint_jsonl.pt (grandes)")
    parser.add_argument("--incluir-checkpoints", action="store_true",
                        help="Incluir os checkpoints grandes (~665 MB cada)")
    parser.add_argument("--dry-run", action="store_true",
                        help="So lista o plano, sem copiar/compactar")
    parser.add_argument("--yes", action="store_true",
                        help="Responde SIM a tudo (nao interativo)")
    parser.add_argument("--quiet", action="store_true", help="Menos saida")
    args = parser.parse_args()
    _inicio = time.time()
    _log("=== EMPACOTAMENTO iniciado | dest=" + (args.dest or "(interativo)")
         + " | checkpoints=" + ("sim" if args.incluir_checkpoints else "nao")
         + " | dry_run=" + str(args.dry_run) + " ===")

    # Seguranca: so roda na raiz do projeto
    if not (RAIZ / "dashboard").is_dir() or not (RAIZ / "rigel.py").exists():
        _log("[ERRO] Execute este script NA RAIZ do projeto RigelSLM.")
        return 1

    # 1) Destino
    if args.dest:
        destino = Path(args.dest)
    elif args.yes:
        destino = RAIZ / "dist"
    else:
        padrao = RAIZ / "dist"
        resp = _perguntar(f"Para qual pasta gerar o ZIP? (ex.: D:\\dist) [{padrao}]: ")
        destino = Path(resp) if resp else padrao
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _log(f"[ERRO] Nao consegui criar a pasta de destino: {e}")
        return 1

    # 2) Checkpoints (opcionais, grandes)
    if args.sem_checkpoints:
        incluir_cp = False
    elif args.incluir_checkpoints:
        incluir_cp = True
    elif args.yes:
        incluir_cp = False
    else:
        resp = _perguntar("Incluir checkpoints grandes (~665 MB cada, continuidade de treino)? (S/N) [N]: ", "N")
        incluir_cp = resp.upper() == "S"

    # 3) Plano
    _log("\n[1/4] Montando o plano do pacote...")
    arquivos = listar_conteudo(incluir_cp)
    if not arquivos:
        _log("[ERRO] Nenhum arquivo para empacotar. Confira o projeto.")
        return 1
    tamanho = sum(p.stat().st_size for p, _ in arquivos)
    _log(f"      {len(arquivos)} arquivos | {tamanho / 1e6:.1f} MB")
    # Detalhamento informativo por area (o que entrou no pacote)
    topos = sorted({rel.split('/')[0] for _, rel in arquivos})
    for t in topos:
        n = sum(1 for _, rel in arquivos if rel.split('/')[0] == t)
        _log(f"        {t}/  -> {n} arquivo(s)")
    _log(f"      plano montado em {time.time() - _inicio:.1f}s")

    if args.dry_run:
        _log("\n=== DRY-RUN (nada foi copiado nem compactado) — encerrando ===")
        return 0

    # 4) Montar + compactar
    _log("[2/4] Copiando para a pasta temporaria...")
    with tempfile.TemporaryDirectory(prefix="rigel_pkg_") as tmp:
        pasta_tmp = Path(tmp)
        try:
            montar_pacote(arquivos, pasta_tmp, quiet=args.quiet)
        except OSError as e:
            _log(f"[ERRO] Falha ao montar o pacote: {e}")
            return 1
        _log(f"      copia concluida em {time.time() - _inicio:.1f}s")

        _log("[3/4] Compactando...")
        zip_path = destino / NOME_ZIP
        if zip_path.exists():
            if args.yes:
                resp = "S"
            else:
                resp = _perguntar(f"'{NOME_ZIP}' ja existe. Sobrescrever? (S/N) [N]: ", "N")
            if resp.upper() != "S":
                _log("Cancelado. Nada foi alterado.")
                return 0
        try:
            total = criar_zip(pasta_tmp, zip_path, quiet=args.quiet)
        except OSError as e:
            _log(f"[ERRO] Falha ao compactar: {e}")
            return 1

    # 5) Resumo
    _duracao = time.time() - _inicio
    _log("\n[4/4] CONCLUIDO!")
    _log(f"  Pacote : {zip_path}")
    _log(f"  Tamanho: {zip_path.stat().st_size / 1e6:.1f} MB ({total} arquivos)")
    _log(f"  Duracao total: {_duracao:.1f}s")
    _log("  Proximo passo: descompacte na maquina alvo e rode")
    _log("     - Windows: executemeprimeiro.bat")
    _log("     - Linux  : ./setup.sh")
    _log("=== EMPACOTAMENTO concluido com sucesso ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
