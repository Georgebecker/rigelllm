from fastapi import APIRouter, BackgroundTasks
from pathlib import Path
import subprocess
import psutil

router = APIRouter(prefix="/train", tags=["Treinamento"])

@router.get("/status")
async def train_status():
    processed = Path("dados/processed")
    files = len(list(processed.glob("**/*.txt"))) if processed.exists() else 0
    return {
        "files_total": files,
        "model_exists": Path("modelo/modelo_melhor.pt").exists(),
        "cpu_usage": psutil.cpu_percent(),
        "memory_usage": psutil.virtual_memory().percent
    }

@router.post("/start")
async def start_training(folders: list[str], background_tasks: BackgroundTasks):
    cmd = ["python", "src/treino.py", "--max-arquivos", "20000"]
    if folders:
        cmd.extend(["--dados", ",".join(folders)])
    
    background_tasks.add_task(subprocess.run, cmd, capture_output=True)
    return {"status": "started", "message": "Treinamento iniciado em background"}