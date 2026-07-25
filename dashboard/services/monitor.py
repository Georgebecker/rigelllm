"""Serviços de monitoramento: CPU por núcleo, I/O, logs ao vivo"""
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