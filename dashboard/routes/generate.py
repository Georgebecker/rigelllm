"""Rota de Geração de Dados - Diálogos, processamento local, downdata"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import subprocess
from datetime import datetime

from dashboard.services.runner import stream_subprocess_to_log

router = APIRouter(prefix="/api/generate", tags=["Geração de Dados"])

BASE_DIR = Path(__file__).parent.parent.parent
GERADOS_DIR = BASE_DIR / "dados" / "gerados"
LOGS_DIR = BASE_DIR / "logs"


class ScriptRequest(BaseModel):
    script: str


class DialogosRequest(BaseModel):
    quantidade: int = 100
    tipo: str = "auto"


class DialogosV1Request(BaseModel):
    quantidade: int = 100


def contar_arquivos_gerados():
    """Conta todos os arquivos gerados por categoria."""
    stats = {}
    if GERADOS_DIR.exists():
        for pasta in sorted(GERADOS_DIR.iterdir()):
            if pasta.is_dir() and pasta.name not in ("logs", "estado"):
                qtde = len(list(pasta.glob("*.txt")))
                if qtde > 0:
                    stats[pasta.name] = qtde
    return stats


def _log_comando(comando: str):
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "dashboard.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {comando}\n")


@router.get("/status")
async def generate_status():
    """Status dos dados gerados."""
    return {
        "arquivos_por_categoria": contar_arquivos_gerados(),
        "total_arquivos": sum(contar_arquivos_gerados().values()),
        "timestamp": datetime.now().isoformat()
    }


@router.post("/dialogos")
async def gerar_dialogos(
    req: DialogosV1Request,
    background_tasks: BackgroundTasks,
):
    """Gera diálogos sintéticos (dialogos.py v1)."""
    quantidade = req.quantidade
    cmd = ["python", "dialogos.py", "--quantidade", str(quantidade)]
    _log_comando(f"Gerando dialogos v1: {' '.join(cmd)}")
    log_path = LOGS_DIR / "dialogos.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": f"Geração de {quantidade} diálogos (v1) iniciada"}


@router.post("/dialogos2")
async def gerar_dialogos2(
    req: DialogosRequest,
    background_tasks: BackgroundTasks,
):
    """Gera diálogos sintéticos (dialogos2.py v2 com múltiplos tipos)."""
    quantidade = req.quantidade
    tipo = req.tipo
    cmd = ["python", "dialogos2.py", "--quantidade", str(quantidade)]
    if tipo and tipo != "auto":
        cmd.extend(["--tipo", tipo])
    _log_comando(f"Gerando dialogos v2: {' '.join(cmd)}")
    log_path = LOGS_DIR / "dialogos.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": f"Geração de {quantidade} diálogos (v2) iniciada"}


@router.post("/downdata")
async def baixar_dados(
    background_tasks: BackgroundTasks,
):
    """Baixa datasets públicos (downdata.py)."""
    cmd = ["python", "downdata.py"]
    _log_comando(f"Baixando datasets: {' '.join(cmd)}")
    log_path = LOGS_DIR / "downdata.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": "Download de datasets iniciado"}


@router.post("/download_datasets")
async def download_datasets(
    background_tasks: BackgroundTasks,
):
    """Baixa datasets (download_datasets.py)."""
    cmd = ["python", "download_datasets.py"]
    _log_comando(f"Download datasets: {' '.join(cmd)}")
    log_path = LOGS_DIR / "download_datasets.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": "Download de datasets (alternativo) iniciado"}


@router.post("/executar")
async def executar_script(
    req: ScriptRequest,
    background_tasks: BackgroundTasks,
):
    """Executa um script Python local (preparar_dados.py, agrupar.py, ultra.py)."""
    script_path = BASE_DIR / req.script
    if not script_path.exists():
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Script {req.script} não encontrado"})

    # Define argumentos padrão conforme o script
    nome = req.script.lower()
    if "agrupar" in nome:
        cmd = ["python", req.script,
               "--entrada", str(GERADOS_DIR),
               "--saida", str(GERADOS_DIR / "agrupados"),
               "--pares", "500"]
        _log_comando(f"Agrupando arquivos pequenos de {GERADOS_DIR} -> {GERADOS_DIR/'agrupados'}")
    elif "preparar" in nome:
        cmd = ["python", req.script, "--qualificar"]
        _log_comando(f"Preparando dados: qualificar + copiar para dados/processed")
    elif "ultra" in nome:
        cmd = ["python", req.script,
               "--shard-size", "5000",
               "--checkpoint-interval", "100"]
        _log_comando(f"Executando ultra-processamento")
    else:
        cmd = ["python", req.script]
        _log_comando(f"Executando script local: {' '.join(cmd)}")

    log_path = LOGS_DIR / "scripts.log"
    # Escreve o comando no log ANTES de executar
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] >>> CMD: {' '.join(cmd)}\n")
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": f"✅ {req.script} iniciado", "comando": ' '.join(cmd)}
