from fastapi import APIRouter
from pathlib import Path
import subprocess
import psutil
from datetime import datetime

router = APIRouter(prefix="/api/ollama", tags=["Ollama"])

BASE_DIR = Path(__file__).parent.parent.parent
LOG_PATH = BASE_DIR / "logs" / "ollama.log"


def _ollama_process_running() -> bool:
    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            name = (p.info.get('name') or "").lower()
            cmd = " ".join(p.info.get('cmdline') or [])
            if 'ollama' in name or 'ollama' in cmd:
                return True
        except Exception:
            continue
    return False


@router.get('/status')
def status():
    """Retorna se o Ollama está rodando e as últimas linhas do log."""
    running = _ollama_process_running()
    last_lines = ""
    try:
        if LOG_PATH.exists():
            last_lines = LOG_PATH.read_text(encoding='utf-8', errors='ignore').splitlines()[-60:]
    except Exception:
        last_lines = []
    return {"running": running, "log_tail": last_lines, "timestamp": datetime.now().isoformat()}


@router.post('/restart')
def restart():
    """Tenta iniciar o Ollama em background e escreve logs em logs/ollama.log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8', errors='ignore') as f:
            f.write(f"[{datetime.now().isoformat()}] Reiniciando Ollama...\n")
            # Iniciar Ollama em background
            # Usa Popen para não bloquear o servidor
            proc = subprocess.Popen(['ollama', 'serve'], cwd=str(BASE_DIR), stdout=f, stderr=f, shell=False)
        return {"status": "started", "pid": proc.pid}
    except Exception as e:
        return {"status": "error", "message": str(e)}
