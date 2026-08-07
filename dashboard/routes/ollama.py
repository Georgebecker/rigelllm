#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ollama.py - Gerenciamento do Ollama para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pathlib import Path
import asyncio
import subprocess
import psutil
from datetime import datetime
from dashboard.services.monitor import (
    verificar_ollama, obter_status_completo,
    iniciar_ollama, reiniciar_ollama, _matar_processos_ollama
)
from dashboard.services import ollama_modelos

router = APIRouter(prefix="/api/ollama", tags=["Ollama"])

BASE_DIR = Path(__file__).parent.parent.parent
LOG_PATH = BASE_DIR / "logs" / "ollama.log"


def _ollama_process_running() -> bool:
    online, _, _ = verificar_ollama()
    return online


@router.get('/status')
def status():
    """Retorna status completo do Ollama (running, pid, port, erro)."""
    return obter_status_completo()


@router.post('/start')
def start_ollama():
    """Inicia o Ollama serve em background."""
    online, _, pid = verificar_ollama()
    if online:
        return {"status": "already_running", "pid": pid, "message": "Ollama já está rodando."}

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8', errors='ignore') as f:
        f.write(f"[{datetime.now().isoformat()}] Iniciando Ollama via monitor...\n")

    sucesso = iniciar_ollama()
    if sucesso:
        _, _, novo_pid = verificar_ollama()
        return {"status": "started", "pid": novo_pid, "message": "Ollama iniciado com sucesso."}
    else:
        return {"status": "error", "message": "Falha ao iniciar Ollama após múltiplas tentativas."}


@router.post('/stop')
def stop_ollama():
    """Para o processo Ollama."""
    mortos = _matar_processos_ollama()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8', errors='ignore') as f:
        f.write(f"[{datetime.now().isoformat()}] Ollama parado ({mortos} processos mortos).\n")
    return {"status": "stopped", "killed": mortos}


@router.post('/restart')
def restart():
    """Reinicia o Ollama forçadamente (mata + inicia)."""
    with open(LOG_PATH, 'a', encoding='utf-8', errors='ignore') as f:
        f.write(f"[{datetime.now().isoformat()}] Reiniciando Ollama via /restart...\n")

    sucesso = reiniciar_ollama()
    if sucesso:
        _, _, pid = verificar_ollama()
        return {"status": "restarted", "pid": pid, "message": "Ollama reiniciado com sucesso."}
    else:
        return {"status": "error", "message": "Falha ao reiniciar Ollama."}


# ============================================================================
# 📥 Modelos SLM — listar instalados + baixar pré-definidos (página /chat)
# ============================================================================

@router.get('/modelos')
def modelos():
    """Modelos instalados no Ollama."""
    online, _, _ = verificar_ollama()
    instalados = ollama_modelos.listar_modelos() if online else []
    return {
        "online": online,
        "modelos": instalados,
        "sugeridos": ollama_modelos.MODELOS_SUGERIDOS,
    }


@router.post('/pull')
def pull(modelo: str = ""):
    """Inicia o download de um modelo (ex.: llama3.2:3b)."""
    if not modelo:
        return JSONResponse({"ok": False, "mensagem": "Informe o modelo."}, status_code=400)
    return ollama_modelos.baixar(modelo)


@router.get('/pull/status')
def pull_status():
    """Progresso do download em andamento."""
    return ollama_modelos.get_estado()


@router.post('/retomar')
def retomar():
    """Retoma o último download (o Ollama continua de onde parou)."""
    return ollama_modelos.retomar()


@router.post('/pull/limpar')
def pull_limpar():
    """Esquece o último download (estado idle)."""
    return ollama_modelos.limpar_pull()


@router.post('/baixar_sharded')
def baixar_sharded(repo: str = "", quant: str = ""):
    """Baixa um GGUF dividido (sharded) do HF, junta e cria no Ollama."""
    if not repo or not quant:
        return JSONResponse({"ok": False, "mensagem": "Informe repo e quantização."}, status_code=400)
    return ollama_modelos.baixar_sharded(repo, quant)


@router.post('/remover')
def remover(modelo: str = ""):
    """Remove um modelo do Ollama (da lista e do disco) — `ollama rm <modelo>`."""
    if not modelo:
        return JSONResponse({"ok": False, "mensagem": "Informe o modelo."}, status_code=400)
    return ollama_modelos.remover(modelo)


@router.get('/caminho')
def caminho():
    """Pasta onde o Ollama guarda os modelos (env OLLAMA_MODELS ou padrão)."""
    return {"caminho": ollama_modelos.caminho_modelos()}


@router.get('/buscar_modelo')
async def buscar_modelo(q: str = "", limite: int = 10):
    """Busca modelos GGUF no HuggingFace com filtro por RAM da máquina."""
    return await asyncio.to_thread(ollama_modelos.buscar_modelos, q, limite)


@router.get('/quantizar/opcoes')
async def quantizar_opcoes(modelo: str = ""):
    """Quantizações possíveis p/ um modelo instalado (menores + cabem na RAM)."""
    return await asyncio.to_thread(ollama_modelos.opcoes_quantizacao, modelo)


@router.post('/quantizar')
async def quantizar(modelo: str = "", quant: str = ""):
    """Quantiza um modelo instalado localmente (llama-quantize → ollama create)."""
    if not modelo or not quant:
        return JSONResponse({"ok": False, "mensagem": "Informe modelo e quantização."}, status_code=400)
    return ollama_modelos.quantizar(modelo, quant)


@router.get('/quantizar/status')
async def quantizar_status():
    """Progresso da quantização em andamento."""
    return ollama_modelos.get_quant_estado()


@router.get('/acoes')
async def acoes(n: int = 40):
    """📜 Últimas ações/erros dos modelos (log em logs/modelos_acoes.log)."""
    return {"acoes": ollama_modelos.acoes_recentes(n)}
