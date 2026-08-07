#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
monitor.py - Monitoramento do sistema (CPU, RAM, disco) para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
import asyncio
import psutil
import os
from pathlib import Path
from datetime import datetime
from collections import deque

BASE_DIR = Path(__file__).parent.parent.parent

# Cache de logs para evitar ler arquivos grandes repetidamente
_log_cache = {}


async def get_cpu_per_core():
    """Retorna percentual de uso por núcleo de CPU."""
    return await asyncio.to_thread(lambda: psutil.cpu_percent(interval=0.3, percpu=True))


async def get_cpu_freq():
    """Retorna frequência da CPU."""
    freq = await asyncio.to_thread(psutil.cpu_freq)
    if freq:
        return {"current": round(freq.current, 1), "max": round(freq.max, 1)}
    return None


async def get_memory_detail():
    """Retorna memória detalhada."""
    mem = await asyncio.to_thread(psutil.virtual_memory)
    return {
        "percent": mem.percent,
        "used_gb": round(mem.used / (1024**3), 1),
        "total_gb": round(mem.total / (1024**3), 1),
        "available_gb": round(mem.available / (1024**3), 1),
    }


async def get_disk_io():
    """Retorna I/O de disco."""
    io = await asyncio.to_thread(psutil.disk_io_counters)
    if io:
        return {
            "read_mb": round(io.read_bytes / (1024**2), 1),
            "write_mb": round(io.write_bytes / (1024**2), 1),
        }
    return {"read_mb": 0, "write_mb": 0}


def ler_ultimas_linhas(caminho: Path, n: int = 50) -> str:
    """Lê as últimas N linhas de um arquivo de forma eficiente."""
    if not caminho.exists():
        return "[arquivo não encontrado]"
    try:
        # Usa seek para ler do final (rápido para arquivos grandes)
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            # Tenta ler tudo se for pequeno
            f.seek(0, os.SEEK_END)
            tamanho = f.tell()
            if tamanho < 50000:  # < 50KB
                f.seek(0)
                lines = f.readlines()
                return "".join(lines[-n:])
            # Arquivo grande: lê blocos do final
            bloco = 4096
            dados = deque()
            pos = tamanho
            while pos > 0 and len(dados) < n:
                read_size = min(bloco, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)
                dados.extendleft(chunk.splitlines(True))
            return "".join(list(dados)[-n:])
    except Exception as e:
        return f"[erro ao ler log: {e}]"


async def get_ultimas_linhas_log(nome_arquivo: str, n: int = 50) -> dict:
    """Retorna as últimas N linhas de um arquivo de log."""
    # Mapeia nomes conhecidos para caminhos
    mapa = {
        "treino.log": BASE_DIR / "logs" / "treino.log",
        "dashboard.log": BASE_DIR / "logs" / "dashboard.log",
        "metricas.json": BASE_DIR / "logs" / "metricas.json",
        "rss.log": BASE_DIR / "dados" / "gerados" / "logs" / "rss.log",
        "preparar_dados.log": BASE_DIR / "logs" / "preparar_dados.log",
        "dialogos.log": BASE_DIR / "dados" / "gerados" / "logs" / "dialogos.log",
        "conversao.log": BASE_DIR / "logs" / "conversao.log",
        "ollama_create.log": BASE_DIR / "logs" / "ollama_create.log",
        "downdata.log": BASE_DIR / "logs" / "downdata.log",
        "download_datasets.log": BASE_DIR / "logs" / "download_datasets.log",
        "scripts.log": BASE_DIR / "logs" / "scripts.log",
        "uvicorn.log": BASE_DIR / "logs" / "uvicorn.log",
    }
    caminho = mapa.get(nome_arquivo, BASE_DIR / "logs" / nome_arquivo)
    if not caminho.exists():
        # Tenta em dados/gerados/logs
        caminho = BASE_DIR / "dados" / "gerados" / "logs" / nome_arquivo

    return {
        "arquivo": nome_arquivo,
        "conteudo": ler_ultimas_linhas(caminho, n),
        "timestamp": datetime.now().isoformat(),
    }


async def get_full_system_status():
    """Junta todos os indicadores do sistema em uma chamada."""
    cpu_per_core, cpu_freq, memory, disk_io = await asyncio.gather(
        get_cpu_per_core(),
        get_cpu_freq(),
        get_memory_detail(),
        get_disk_io(),
    )
    cpu_avg = round(sum(cpu_per_core) / len(cpu_per_core), 1) if cpu_per_core else 0
    
    # Modelo e dados processados (para compatibilidade com o frontend)
    modelo_melhor = (BASE_DIR / "modelo" / "modelo_melhor.pt").exists()
    processed_dir = BASE_DIR / "dados" / "processed"
    if processed_dir.exists():
        total_arquivos = sum(1 for _ in processed_dir.glob("**/*.txt"))
    else:
        total_arquivos = 0

    return {
        "cpu": {
            "percent": cpu_avg,
            "per_core": [round(c, 1) for c in cpu_per_core],
            "freq": cpu_freq,
            "cores": len(cpu_per_core),
        },
        "memory": memory,
        "disk_io": disk_io,
        "disk": psutil.disk_usage('/').percent,  # Uso total do disco
        "model_exists": modelo_melhor,
        "model_date": datetime.fromtimestamp((BASE_DIR / "modelo" / "modelo_melhor.pt").stat().st_mtime).strftime("%d/%m/%Y %H:%M") if modelo_melhor else None,
        "processed_files": total_arquivos,
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════
# MONITORAMENTO E AUTO-RECUPERAÇÃO DO OLLAMA
# ═══════════════════════════════════════════════

import socket
import subprocess
import signal

OLLAMA_PORT = 11434
OLLAMA_HOST = '127.0.0.1'


def _log_ollama(msg: str):
    """Escreve no log do monitor do Ollama."""
    log_path = BASE_DIR / 'logs' / 'monitor_ollama.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}\n"
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass
    print(f"[MONITOR] {msg}")


def verificar_ollama() -> tuple:
    """
    Verifica se o Ollama está respondendo via socket TCP.
    Retorna (online: bool, erro: str or None, pid: int or None)
    """
    # 1. Teste de socket
    sock_ok = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect((OLLAMA_HOST, OLLAMA_PORT))
            sock_ok = True
    except (socket.timeout, ConnectionRefusedError, OSError):
        pass

    # 2. Procura processo
    pid = None
    for p in psutil.process_iter(['name', 'pid', 'cmdline']):
        try:
            name = (p.info.get('name') or '').lower()
            cmd = ' '.join(p.info.get('cmdline') or [])
            if 'ollama' in name or 'ollama' in cmd:
                pid = p.info['pid']
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if sock_ok:
        return True, None, pid
    elif pid:
        return False, f"Processo ativo (PID {pid}) mas porta {OLLAMA_PORT} fechada", pid
    else:
        return False, "Nenhum processo Ollama encontrado", None


def _matar_processos_ollama() -> int:
    """Mata processos relacionados ao Ollama usando SIGTERM e taskkill.

    ⚠️ Só mata processos do Ollama DE VERDADE (ollama.exe / ollama_llama_server
    / `ollama serve`). Antes matava QUALQUER processo que tivesse a palavra
    "ollama" no comando — derrubava scripts de teste/diagnóstico do usuário.
    """
    mortos = 0
    for p in psutil.process_iter(['name', 'pid', 'exe', 'cmdline']):
        try:
            name = (p.info.get('name') or '').lower()
            exe = (p.info.get('exe') or '').lower()
            cmd = ' '.join(p.info.get('cmdline') or []).lower()
            eh_ollama = (
                name in ('ollama.exe', 'ollama', 'ollama_llama_server.exe', 'ollama_llama_server')
                or '\\ollama.exe' in exe
                or '\\ollama_llama_server.exe' in exe
                or cmd.startswith('ollama ')
                or 'ollama serve' in cmd
            )
            if eh_ollama:
                try:
                    os.kill(p.info['pid'], signal.SIGTERM)
                    mortos += 1
                except (OSError, PermissionError):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'],
                           capture_output=True, timeout=5)
        except Exception:
            pass
    return mortos


def iniciar_ollama() -> bool:
    """
    Tenta iniciar o Ollama serve.
    Retorna True se conseguiu, False caso contrário.
    """
    _log_ollama("Tentando iniciar Ollama...")

    # Mata processos antigos
    mortos = _matar_processos_ollama()
    if mortos:
        _log_ollama(f"Matou {mortos} processo(s) antigo(s)")
    import time as _time
    _time.sleep(2)

    # Inicia novo processo
    try:
        proc = subprocess.Popen(
            ['ollama', 'serve'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        _log_ollama(f"Ollama iniciado (PID {proc.pid})")
    except FileNotFoundError:
        _log_ollama("ERRO: Comando 'ollama' não encontrado no PATH")
        return False
    except Exception as e:
        _log_ollama(f"ERRO ao iniciar Ollama: {e}")
        return False

    # Aguarda ficar pronto (até ~12s)
    for tentativa in range(6):
        _time.sleep(2)
        online, erro, pid = verificar_ollama()
        if online:
            _log_ollama(f"Ollama pronto (PID {pid}) após {tentativa + 1}s")
            return True
        _log_ollama(f"Aguardando Ollama... ({tentativa + 1}/6)")

    _log_ollama("ERRO: Ollama não ficou pronto após 12s")
    return False


def reiniciar_ollama() -> bool:
    """Reinicia o Ollama forçadamente."""
    _log_ollama("Iniciando reinicialização...")
    online, _, _ = verificar_ollama()
    if online:
        _log_ollama("Ollama estava online, será desligado")
        _matar_processos_ollama()
        import time as _t
        _t.sleep(2)
    return iniciar_ollama()


def obter_status_completo() -> dict:
    """Retorna status completo do Ollama para API."""
    online, erro, pid = verificar_ollama()
    return {
        "running": online,
        "pid": pid,
        "port": OLLAMA_PORT if online else None,
        "host": OLLAMA_HOST,
        "erro": erro,
        "timestamp": datetime.now().isoformat()
    }