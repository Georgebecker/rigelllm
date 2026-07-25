"""Rota de Treinamento - Iniciar, monitorar progresso real"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import subprocess
from subprocess import Popen, PIPE, STDOUT
import json
import re
from datetime import datetime
from dashboard.services.monitor import ler_ultimas_linhas
from dashboard.services.runner import stream_subprocess_to_log

router = APIRouter(prefix="/api/train", tags=["Treinamento"])

BASE_DIR = Path(__file__).parent.parent.parent
PROCESSED_DIR = BASE_DIR / "dados" / "processed"
MODEL_DIR = BASE_DIR / "modelo"
METRICAS_PATH = BASE_DIR / "logs" / "metricas.json"
ESTADO_PATH = MODEL_DIR / "estado_treino.json"
TREINO_LOG_PATH = BASE_DIR / "logs" / "treino.log"


class TreinoRequest(BaseModel):
    pastas: list[str] | None = None
    max_arquivos: int = 20000
    resume: bool = False
    epochs: int = 20


def listar_pastas_disponiveis():
    if not PROCESSED_DIR.exists():
        return []
    pastas = []
    for item in sorted(PROCESSED_DIR.iterdir()):
        if item.is_dir():
            qtde = len(list(item.glob("*.txt")))
            if qtde > 0:
                pastas.append({"nome": item.name, "arquivos": qtde})
    return pastas


def _stream_process_to_log(cmd, cwd=None, log_path: Path = TREINO_LOG_PATH):
    """Executa o comando e escreve stdout/stderr em tempo real no arquivo de log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
        f.write(f"[{datetime.now().isoformat()}] >>> CMD: {' '.join(cmd)}\n")
        try:
            proc = Popen(cmd, cwd=str(cwd) if cwd else None, stdout=PIPE, stderr=STDOUT, text=True)
            if proc.stdout:
                for linha in proc.stdout:
                    f.write(linha)
                    f.flush()
            proc.wait()
            f.write(f"[{datetime.now().isoformat()}] <<< Processo finalizado com código {proc.returncode}\n")
        except Exception as e:
            f.write(f"[{datetime.now().isoformat()}] ERRO ao executar comando: {e}\n")
            f.flush()


def carregar_metricas():
    if METRICAS_PATH.exists():
        try:
            data = json.loads(METRICAS_PATH.read_text(encoding="utf-8"))
            return data.get("historico", [])
        except Exception:
            return []
    return []


def carregar_estado():
    if ESTADO_PATH.exists():
        try:
            return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def extrair_progresso_treino(log_texto: str) -> dict:
    """Extrai época atual, batch, loss do log de treino."""
    progresso = {"em_andamento": False, "epoch_atual": None, "total_epochs": None,
                  "batch_atual": None, "loss_atual": None, "percentual": 0}
    if not log_texto:
        return progresso

    # Procura padrões como "Epoch 5/20" ou "Batch 123/500"
    for linha in reversed(log_texto.splitlines()):
        ep = re.search(r"Epoch\s*(\d+)\s*/\s*(\d+)", linha, re.IGNORECASE)
        if ep:
            progresso["epoch_atual"] = int(ep.group(1))
            progresso["total_epochs"] = int(ep.group(2))
            progresso["em_andamento"] = True
            if progresso["total_epochs"]:
                progresso["percentual"] = round(progresso["epoch_atual"] / progresso["total_epochs"] * 100, 1)
        bt = re.search(r"Batch\s*(\d+)\s*/\s*(\d+)", linha, re.IGNORECASE)
        if bt:
            progresso["batch_atual"] = int(bt.group(1))
        loss = re.search(r"(?:loss|loss:)\s*([\d.]+)", linha, re.IGNORECASE)
        if loss and not progresso.get("loss_atual"):
            progresso["loss_atual"] = float(loss.group(1))

    # Verifica se o processo ainda está rodando (últimas linhas têm timestamps recentes)
    # Detecta mensagens de finalização de treino no log (português/inglês)
    termino = re.search(r"(TREINO CONCLU|TREINO COMPLET|TRAIN (FINISHED|COMPLETED)|TREINO CONCLU\w+|TREINO COMPLETO|TREINO CONCLUIDO)", log_texto, re.IGNORECASE)
    if termino:
        progresso["em_andamento"] = False
        progresso["percentual"] = 100
        # tenta preencher epoch_atual com total_epochs se encontrado antes
        if progresso.get("total_epochs") and not progresso.get("epoch_atual"):
            progresso["epoch_atual"] = progresso["total_epochs"]
    else:
        if progresso["em_andamento"]:
            linhas_recentes = [l for l in log_texto.splitlines() if l.strip()][-5:]
            if linhas_recentes:
                progresso["ultimas_linhas"] = linhas_recentes[-3:]
    return progresso


@router.get("/status")
async def train_status():
    """Status com progresso real extraído do log."""
    pastas = listar_pastas_disponiveis()
    metricas = carregar_metricas()
    estado = carregar_estado()
    log_texto = ler_ultimas_linhas(TREINO_LOG_PATH, 100)
    progresso = extrair_progresso_treino(log_texto)

    return {
        "pastas_disponiveis": pastas,
        "total_arquivos": sum(p["arquivos"] for p in pastas),
        "total_pastas": len(pastas),
        "modelo_existe": (MODEL_DIR / "modelo_melhor.pt").exists(),
        "checkpoint_existe": (MODEL_DIR / "checkpoint.pt").exists(),
        "ultima_epoch": estado.get("epoch", 0),
        "melhor_loss": estado.get("best_val_loss"),
        "historico_metricas": metricas[-15:],
        "progresso": progresso,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/start")
async def start_training(
    req: TreinoRequest,
    background_tasks: BackgroundTasks,
):
    cmd = ["python", "treino.py", "--max-arquivos", str(req.max_arquivos)]
    if req.pastas and len(req.pastas) > 0:
        cmd.extend(["--dados", ",".join(req.pastas)])
    if req.resume:
        cmd.append("--resume")

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "dashboard.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Iniciando treino: {' '.join(cmd)}\n")

    # Executa o treino em background e streama a saída para o log de treino
    background_tasks.add_task(_stream_process_to_log, cmd, BASE_DIR, TREINO_LOG_PATH)
    return {"status": "started", "message": f"Treinamento iniciado: {req.max_arquivos} arquivos",
            "timestamp": datetime.now().isoformat()}


@router.post("/stop")
async def stop_training():
    stop_file = BASE_DIR / "modelo" / "STOP_TREINO.signal"
    stop_file.write_text(datetime.now().isoformat())
    return {"status": "stopping", "message": "Sinal de parada enviado"}


@router.get("/progresso")
async def progresso_treino():
    """Apenas o progresso atual (para polling frequente)."""
    log_texto = ler_ultimas_linhas(TREINO_LOG_PATH, 80)
    progresso = extrair_progresso_treino(log_texto)
    return {"progresso": progresso, "timestamp": datetime.now().isoformat()}


@router.get("/logs")
async def treino_logs():
    """Últimas linhas do log de treino."""
    return {"conteudo": ler_ultimas_linhas(TREINO_LOG_PATH, 60)}
