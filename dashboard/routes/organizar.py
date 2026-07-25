from fastapi import APIRouter, BackgroundTasks, HTTPException
import subprocess
import os
import json
import sys
from datetime import datetime

router = APIRouter(prefix="/api/organizar", tags=["organizar"])

ORGANIZAR_SCRIPT = "organizar_pastas.py"
REGISTRO_PATH = "registro_pastas.json"
STATUS_FILE = "organizar_status.json"

def ler_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"running": False, "pid": None, "log": "", "started": "", "finished": False}

def escrever_status(status):
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(status, f, indent=2)

@router.post("/executar")
async def executar_organizador(background_tasks: BackgroundTasks, apenas_registro: bool = False):
    status = ler_status()
    if status.get("running"):
        raise HTTPException(status_code=409, detail="Organizador já está em execução.")
    
    cmd = [sys.executable, ORGANIZAR_SCRIPT]
    if apenas_registro:
        cmd.append("--apenas-registro")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    status = {
        "running": True,
        "pid": process.pid,
        "log": "",
        "started": datetime.now().isoformat(),
        "finished": False
    }
    escrever_status(status)
    
    def coletar_log():
        for line in process.stdout:
            status = ler_status()
            status["log"] += line
            escrever_status(status)
        process.wait()
        status = ler_status()
        status["running"] = False
        status["finished"] = True
        escrever_status(status)
    
    background_tasks.add_task(coletar_log)
    return {"message": "Organizador iniciado", "pid": process.pid}

@router.get("/status")
async def status_organizador():
    return ler_status()

@router.get("/registro")
async def obter_registro():
    if not os.path.exists(REGISTRO_PATH):
        return {"erro": "Registro não encontrado. Execute o organizador primeiro."}
    with open(REGISTRO_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)