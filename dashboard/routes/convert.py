"""Rota de Conversão GGUF - Converter modelo .pt para GGUF"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import subprocess
import json
from datetime import datetime

from dashboard.services.runner import stream_subprocess_to_log

router = APIRouter(prefix="/api/convert", tags=["Conversão GGUF"])

BASE_DIR = Path(__file__).parent.parent.parent
MODEL_DIR = BASE_DIR / "modelo"
LOGS_DIR = BASE_DIR / "logs"


class ConvertRequest(BaseModel):
    modelo: str = "modelo_melhor.pt"
    quantizacao: str = "Q4_K"


@router.get("/status")
async def convert_status():
    """Status dos modelos e conversões disponíveis."""
    modelos = []
    for f in ["modelo.pt", "modelo_melhor.pt", "checkpoint.pt"]:
        path = MODEL_DIR / f
        if path.exists():
            modelos.append({
                "nome": f,
                "tamanho_mb": round(path.stat().st_size / (1024 * 1024), 1),
                "data": datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            })

    # Verifica GGUF já convertidos
    ggufs = []
    gguf_dir = BASE_DIR / "gguf"
    if gguf_dir.exists():
        for f in gguf_dir.glob("*.gguf"):
            ggufs.append({
                "nome": f.name,
                "tamanho_mb": round(f.stat().st_size / (1024 * 1024), 1)
            })

    return {
        "modelos_disponiveis": modelos,
        "ggufs_existentes": ggufs,
        "pode_converter": len(modelos) > 0,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/start")
async def start_conversion(
    req: ConvertRequest,
    background_tasks: BackgroundTasks,
):
    """Inicia a conversão de um modelo .pt para GGUF."""
    modelo = req.modelo
    quantizacao = req.quantizacao
    modelo_path = MODEL_DIR / modelo
    if not modelo_path.exists():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Modelo {modelo} não encontrado"}
        )

    cmd = [
        "python", "src/converter_para_gguf.py",
        "--model", str(modelo_path),
        "--quant", quantizacao
    ]

    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "dashboard.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Iniciando conversão: {' '.join(cmd)}\n")

    log_path = LOGS_DIR / "conversao.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {
        "status": "started",
        "message": f"Conversão de {modelo} para GGUF ({quantizacao}) iniciada",
        "timestamp": datetime.now().isoformat()
    }


@router.post("/criar-ollama")
async def criar_modelo_ollama(background_tasks: BackgroundTasks):
    """Cria um modelo Ollama a partir do GGUF (rigelslm_Q4_K.gguf)."""
    gguf_path = BASE_DIR / "gguf" / "rigelslm_Q4_K.gguf"
    if not gguf_path.exists():
        return JSONResponse(status_code=400, content={"status": "error", "message": "GGUF não encontrado"})

    modelfile_content = f"FROM {gguf_path}\n"
    modelfile_path = BASE_DIR / "gguf" / "Modelfile"
    modelfile_path.write_text(modelfile_content, encoding="utf-8")

    cmd = ["ollama", "create", "rigelslm", "-f", str(modelfile_path)]

    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "dashboard.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Criando modelo Ollama: {' '.join(cmd)}\n")

    log_path = LOGS_DIR / "ollama_create.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {
        "status": "started",
        "message": "Criação do modelo Ollama 'rigelslm' iniciada a partir do GGUF",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/versoes")
async def versoes_modelos():
    """Histórico de versões dos modelos."""
    metadados_path = MODEL_DIR / "versoes.json"
    if metadados_path.exists():
        try:
            return json.loads(metadados_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    versoes = []
    for f in sorted(MODEL_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix in (".pt", ".gguf"):
            versoes.append({
                "nome": f.name,
                "tamanho_mb": round(f.stat().st_size / (1024 * 1024), 1),
                "data": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "tipo": "GGUF" if f.suffix == ".gguf" else "PyTorch"
            })

    return {"versoes": versoes}
