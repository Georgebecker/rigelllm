import psutil
import asyncio
from datetime import datetime
from pathlib import Path
import os

# Cache para evitar polling excessivo
_cache = {}
_cache_time = 0

def get_full_status():
    global _cache, _cache_time
    now = datetime.now().timestamp()
    # Atualiza a cada 2 segundos
    if now - _cache_time < 2:
        return _cache

    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.3)
    cpu_freq = psutil.cpu_freq()
    cpu_cores = psutil.cpu_count(logical=True)
    cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)

    # Memória
    mem = psutil.virtual_memory()
    mem_total_gb = mem.total / (1024**3)
    mem_used_gb = mem.used / (1024**3)
    mem_percent = mem.percent

    # Disco
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    disk_io = psutil.disk_io_counters()
    if disk_io:
        read_mb = disk_io.read_bytes / (1024**2)
        write_mb = disk_io.write_bytes / (1024**2)
    else:
        read_mb = 0
        write_mb = 0

    # Modelo
    modelo_melhor = Path("modelo/modelo_melhor.pt").exists()
    modelo_gguf = any(Path("gguf").glob("*.gguf")) if Path("gguf").exists() else False

    # Dados processados
    processed_dir = Path("dados/processed")
    if processed_dir.exists():
        # Conta arquivos recursivamente
        total_arquivos = sum(1 for _ in processed_dir.glob("**/*.txt"))
    else:
        total_arquivos = 0

    # Timestamp
    timestamp = datetime.now().isoformat()

    _cache = {
        "cpu": {
            "percent": round(cpu_percent, 1),
            "cores": cpu_cores,
            "freq_mhz": round(cpu_freq.current, 0) if cpu_freq else 0,
            "per_core": [round(p, 1) for p in cpu_per_core]
        },
        "memory": {
            "total_gb": round(mem_total_gb, 1),
            "used_gb": round(mem_used_gb, 1),
            "percent": round(mem_percent, 1)
        },
        "disk": round(disk_percent, 1),
        "disk_io": {
            "read_mb": round(read_mb, 0),
            "write_mb": round(write_mb, 0)
        },
        "model_exists": modelo_melhor,
        "model_date": datetime.fromtimestamp(Path("modelo/modelo_melhor.pt").stat().st_mtime).strftime("%d/%m/%Y %H:%M") if modelo_melhor else None,
        "processed_files": total_arquivos,
        "timestamp": timestamp,
        "gguf_exists": modelo_gguf
    }
    _cache_time = now
    return _cache

def get_ultimas_linhas_log(arquivo, linhas=50):
    """Retorna as últimas linhas de um arquivo de log."""
    log_dir = Path("logs")
    caminho = log_dir / arquivo
    if not caminho.exists():
        return {"erro": f"Arquivo {arquivo} não encontrado"}
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            todas = f.readlines()
        ultimas = todas[-linhas:] if todas else []
        return {"conteudo": "".join(ultimas)}
    except Exception as e:
        return {"erro": str(e)}