#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
converter_state.py - Gerenciamento de estado da conversão GGUF em tempo real
Versão: 1.0.0 | Data: 31/07/2026

Mantém o estado da conversão em memória para feedback via polling no frontend.
"""
import json
import threading
import subprocess
from subprocess import Popen, PIPE, STDOUT
from pathlib import Path
from datetime import datetime
from typing import Optional

# =============================================================================
# ESTADO GLOBAL DA CONVERSÃO (thread-safe)
# =============================================================================

_conversion_state = {
    "running": False,
    "pid": None,
    "start_time": None,
    "end_time": None,
    "status": "idle",  # idle | running | completed | failed | cancelled
    "exit_code": None,
    "progress_pct": 0,
    "stage": "",
    "message": "",
    "log_lines": [],
    "modelo": "",
    "quantizacao": "",
    "gguf_path": None,
    "tamanho_mb": None,
}
_conversion_lock = threading.Lock()

_ollama_state = {
    "running": False,
    "start_time": None,
    "end_time": None,
    "status": "idle",
    "exit_code": None,
    "log_lines": [],
    "last_create": None,  # dict com info da última criação bem-sucedida
}
_ollama_lock = threading.Lock()

# Persistência da última criação (sobrevive a reinícios do dashboard)
_ESTADO_DIR = Path(__file__).resolve().parent.parent.parent / "estado"
_OLLAMA_HISTORICO = _ESTADO_DIR / "ollama_ultima_criacao.json"


def get_conversion_state():
    """Retorna cópia do estado atual da conversão."""
    with _conversion_lock:
        return dict(_conversion_state)


def update_conversion_state(**kwargs):
    """Atualiza campos do estado da conversão de forma thread-safe."""
    with _conversion_lock:
        for k, v in kwargs.items():
            if k in _conversion_state:
                _conversion_state[k] = v


def append_conversion_log(line: str):
    """Adiciona linha ao log e mantém apenas as últimas 200 linhas."""
    with _conversion_lock:
        _conversion_state["log_lines"].append(line)
        if len(_conversion_state["log_lines"]) > 200:
            _conversion_state["log_lines"] = _conversion_state["log_lines"][-200:]


def reset_conversion_state():
    """Reseta o estado para idle."""
    with _conversion_lock:
        _conversion_state["running"] = False
        _conversion_state["pid"] = None
        _conversion_state["start_time"] = None
        _conversion_state["end_time"] = None
        _conversion_state["status"] = "idle"
        _conversion_state["exit_code"] = None
        _conversion_state["progress_pct"] = 0
        _conversion_state["stage"] = ""
        _conversion_state["message"] = ""
        _conversion_state["log_lines"] = []
        _conversion_state["modelo"] = ""
        _conversion_state["quantizacao"] = ""
        _conversion_state["gguf_path"] = None
        _conversion_state["tamanho_mb"] = None


# =============================================================================
# ESTADO DA CRIAÇÃO OLLAMA
# =============================================================================

def get_ollama_state():
    """Retorna cópia do estado atual da criação Ollama."""
    with _ollama_lock:
        return dict(_ollama_state)


def update_ollama_state(**kwargs):
    """Atualiza campos do estado Ollama de forma thread-safe."""
    with _ollama_lock:
        for k, v in kwargs.items():
            if k in _ollama_state:
                _ollama_state[k] = v


def append_ollama_log(line: str):
    """Adiciona linha ao log Ollama."""
    with _ollama_lock:
        _ollama_state["log_lines"].append(line)
        if len(_ollama_state["log_lines"]) > 200:
            _ollama_state["log_lines"] = _ollama_state["log_lines"][-200:]


def reset_ollama_state():
    """Reseta o estado Ollama para idle."""
    with _ollama_lock:
        _ollama_state["running"] = False
        _ollama_state["start_time"] = None
        _ollama_state["end_time"] = None
        _ollama_state["status"] = "idle"
        _ollama_state["exit_code"] = None
        _ollama_state["log_lines"] = []


def _gguf_do_modelfile(cmd):
    """Extrai o caminho do GGUF a partir do comando 'ollama create -f <Modelfile>'."""
    try:
        for i, arg in enumerate(cmd):
            if arg == "-f" and i + 1 < len(cmd):
                mf = Path(cmd[i + 1])
                if mf.exists():
                    for linha in mf.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if linha.strip().upper().startswith("FROM "):
                            return Path(linha.split(" ", 1)[1].strip().strip('"'))
    except Exception:
        pass
    return None


def set_ollama_last_create(info: dict):
    """Registra a última criação bem-sucedida no Ollama (memória + disco)."""
    with _ollama_lock:
        _ollama_state["last_create"] = info
    try:
        _OLLAMA_HISTORICO.parent.mkdir(parents=True, exist_ok=True)
        _OLLAMA_HISTORICO.write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_ollama_last_create():
    """Retorna a última criação persistida (ou None)."""
    try:
        if _OLLAMA_HISTORICO.exists():
            return json.loads(_OLLAMA_HISTORICO.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


# =============================================================================
# EXECUTOR DE CONVERSÃO COM FEEDBACK
# =============================================================================

def run_conversion_with_progress(cmd, cwd, log_path, modelo, quantizacao):
    """Executa a conversão e atualiza o estado em tempo real."""
    reset_conversion_state()
    update_conversion_state(
        running=True,
        start_time=datetime.now().isoformat(),
        status="running",
        progress_pct=0,
        stage="iniciando",
        message="Preparando conversão...",
        modelo=modelo,
        quantizacao=quantizacao,
    )

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Map regex de estágios para percentuais aproximados
    stage_map = [
        (r"Verificando dependências|dependências", 2, "dependências"),
        (r"Instalando", 3, "instalando dependências"),
        (r"Modelo:", 5, "modelo localizado"),
        (r"Vocab detectado", 8, "analisando vocabulário"),
        (r"Tokenizer carregado", 12, "tokenizer carregado"),
        (r"Carregando pesos", 15, "carregando pesos"),
        (r"Truncando embedding", 18, "ajustando embedding"),
        (r"Mapeando tensores", 25, "mapeando tensores"),
        (r"tensores mapeados", 35, "tensores prontos"),
        (r"Gerando GGUF", 40, "gerando arquivo GGUF"),
        (r"Tokenizer exportado", 50, "exportando tokenizer"),
        (r"Adicionando tensor|blk\.", 60, "adicionando tensores"),
        (r"GGUF gerado:", 85, "GGUF gerado"),
        (r"Gerando Modelfile", 90, "gerando Modelfile"),
        (r"CONVERSÃO CONCLUÍDA", 100, "concluída"),
    ]

    try:
        with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
            f.write(f"[{datetime.now().isoformat()}] >>> CMD: {' '.join(cmd)}\n")

            env = None
            if cmd and ('python' in str(cmd[0]).lower()):
                import os as _os
                env = dict(_os.environ)
                env['PYTHONIOENCODING'] = 'utf-8'

            proc = Popen(
                cmd, cwd=str(cwd) if cwd else None,
                stdout=PIPE, stderr=STDOUT,
                encoding='utf-8', errors='replace', env=env
            )

            update_conversion_state(pid=proc.pid)

            import re
            if proc.stdout:
                for linha in proc.stdout:
                    linha = linha.rstrip('\n\r')
                    f.write(linha + "\n")
                    f.flush()

                    # Atualiza progresso baseado em palavras-chave
                    pct_atual = _conversion_state.get("progress_pct", 0)
                    for pattern, pct, stage in stage_map:
                        if re.search(pattern, linha, re.IGNORECASE):
                            if pct > pct_atual:
                                update_conversion_state(
                                    progress_pct=pct,
                                    stage=stage,
                                    message=linha.strip()
                                )
                            break

                    # Detecta conclusão bem-sucedida
                    if "CONVERSÃO CONCLUÍDA" in linha.upper():
                        update_conversion_state(progress_pct=100, stage="concluída")

                    append_conversion_log(linha)

            proc.wait()
            exit_code = proc.returncode

            f.write(f"[{datetime.now().isoformat()}] <<< CODIGO: {exit_code}\n")

            if exit_code == 0:
                # Tenta detectar o GGUF gerado
                gguf_path = None
                tamanho_mb = None
                for line in _conversion_state.get("log_lines", []):
                    if "GGUF gerado:" in line:
                        parts = line.split("GGUF gerado:")
                        if len(parts) > 1:
                            gguf_path = parts[1].strip()
                    if "Tamanho:" in line:
                        try:
                            size_str = line.split("Tamanho:")[1].strip().replace("MB", "").strip()
                            tamanho_mb = float(size_str)
                        except:
                            pass

                update_conversion_state(
                    running=False,
                    end_time=datetime.now().isoformat(),
                    status="completed",
                    exit_code=0,
                    progress_pct=100,
                    stage="concluída",
                    message="✅ Conversão concluída com sucesso!",
                    gguf_path=gguf_path,
                    tamanho_mb=tamanho_mb,
                )
            else:
                update_conversion_state(
                    running=False,
                    end_time=datetime.now().isoformat(),
                    status="failed",
                    exit_code=exit_code,
                    stage="erro",
                    message=f"❌ Conversão falhou com código {exit_code}",
                )

    except Exception as e:
        error_msg = f"Erro ao executar conversão: {e}"
        append_conversion_log(error_msg)
        update_conversion_state(
            running=False,
            end_time=datetime.now().isoformat(),
            status="failed",
            exit_code=-1,
            stage="erro",
            message=f"❌ {error_msg}",
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] ERRO: {e}\n")


def run_ollama_create_with_progress(cmd, cwd, log_path):
    """Executa ollama create e atualiza o estado em tempo real."""
    reset_ollama_state()
    update_ollama_state(
        running=True,
        start_time=datetime.now().isoformat(),
        status="running",
    )

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
            f.write(f"[{datetime.now().isoformat()}] >>> CMD: {' '.join(cmd)}\n")

            proc = Popen(
                cmd, cwd=str(cwd) if cwd else None,
                stdout=PIPE, stderr=STDOUT,
                encoding='utf-8', errors='replace'
            )

            if proc.stdout:
                for linha in proc.stdout:
                    linha = linha.rstrip('\n\r')
                    f.write(linha + "\n")
                    f.flush()
                    append_ollama_log(linha)

            proc.wait()
            exit_code = proc.returncode

            f.write(f"[{datetime.now().isoformat()}] <<< CODIGO: {exit_code}\n")

            if exit_code == 0:
                # Último log indica sucesso
                last_lines = _ollama_state.get("log_lines", [])
                success = any("success" in line.lower() for line in last_lines)

                if success:
                    update_ollama_state(
                        running=False,
                        end_time=datetime.now().isoformat(),
                        status="completed",
                        exit_code=0,
                    )
                    # Registra a criação (com o GGUF que originou o modelo)
                    gguf = _gguf_do_modelfile(cmd)
                    gguf_nome = gguf.name if gguf else ""
                    gguf_mb = None
                    if gguf and gguf.exists():
                        gguf_mb = round(gguf.stat().st_size / (1024 * 1024), 1)
                    set_ollama_last_create({
                        "data": datetime.now().isoformat(),
                        "modelo": "rigelslm",
                        "status": "success",
                        "gguf": gguf_nome,
                        "gguf_path": str(gguf) if gguf else "",
                        "tamanho_mb": gguf_mb,
                        "log_resumo": last_lines[-3:] if len(last_lines) >= 3 else last_lines,
                    })
                else:
                    update_ollama_state(
                        running=False,
                        end_time=datetime.now().isoformat(),
                        status="failed",
                        exit_code=exit_code,
                    )
            else:
                update_ollama_state(
                    running=False,
                    end_time=datetime.now().isoformat(),
                    status="failed",
                    exit_code=exit_code,
                )

    except Exception as e:
        error_msg = f"Erro ao criar modelo Ollama: {e}"
        append_ollama_log(error_msg)
        update_ollama_state(
            running=False,
            end_time=datetime.now().isoformat(),
            status="failed",
            exit_code=-1,
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] ERRO: {e}\n")
