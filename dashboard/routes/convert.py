#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
convert.py - Conversão .pt → GGUF para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel
from pathlib import Path
import subprocess
import json
import socket
from datetime import datetime
from urllib.parse import quote, unquote
import threading

from dashboard.services.runner import stream_subprocess_to_log
from dashboard.services.converter_state import (
    get_conversion_state, update_conversion_state, reset_conversion_state,
    get_ollama_state, update_ollama_state, reset_ollama_state,
    run_conversion_with_progress, run_ollama_create_with_progress,
)

router = APIRouter(prefix="/api/convert", tags=["Conversão GGUF"])

BASE_DIR = Path(__file__).parent.parent.parent
MODEL_DIR = BASE_DIR / "modelo"
LOGS_DIR = BASE_DIR / "logs"
GGUF_DIR = BASE_DIR / "gguf"

# Descrição dos modelos .pt (mostrada como tooltip na página de conversão)
DESCRICOES_MODELOS = {
    "modelo.pt": "Modelo FINAL salvo ao fim de cada treino (pesos limpos). "
                 "Alternativa segura para conversão.",
    "modelo_melhor.pt": "Melhor modelo por VALIDAÇÃO durante o treino. "
                         "RECOMENDADO para conversão.",
    "checkpoint.pt": "Checkpoint de RETOMADA do treino CAUSAL (contém optimizer/época/estado). "
                      "Serve para retomar um treino interrompido — NÃO converter.",
    "checkpoint_jsonl.pt": "Checkpoint de RETOMADA do treino SFT/JSONL (contém optimizer/época/estado). "
                            "Serve para retomar um treino interrompido — NÃO converter.",
}
RECOMENDADOS_MODELOS = {"modelo_melhor.pt"}


def _ip_rede_local() -> str:
    """IP da máquina na rede local (para o celular baixar o GGUF via QR)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _caminho_gguf_seguro(nome: str) -> Path | None:
    """Resolve um nome de GGUF garantindo que está dentro de gguf/ (anti path traversal)."""
    nome = unquote(nome).replace("\\", "/").split("/")[-1]
    if not nome.lower().endswith(".gguf"):
        return None
    caminho = (GGUF_DIR / nome).resolve()
    base = GGUF_DIR.resolve()
    if str(caminho) != str(base) and not str(caminho).startswith(str(base) + chr(92)):
        return None
    return caminho


@router.get("/download/{nome}")
async def download_gguf(nome: str):
    """📥 Baixa um GGUF da pasta gguf/ (funciona no CELULAR pela mesma rede)."""
    caminho = _caminho_gguf_seguro(nome)
    if caminho is None:
        return JSONResponse({"ok": False, "erro": "Só arquivos .gguf da pasta gguf/."},
                            status_code=400)
    if not caminho.is_file():
        return JSONResponse({"ok": False, "erro": "GGUF não encontrado."},
                            status_code=404)
    return FileResponse(path=str(caminho), media_type="application/octet-stream",
                        filename=caminho.name)


@router.get("/qr/{nome}")
async def qr_gguf(nome: str):
    """📱 Gera o QR code do download do GGUF (o celular escaneia e baixa)."""
    caminho = _caminho_gguf_seguro(nome)
    if caminho is None:
        return JSONResponse({"ok": False, "erro": "Só arquivos .gguf da pasta gguf/."},
                            status_code=400)
    if not caminho.is_file():
        return JSONResponse({"ok": False, "erro": "GGUF não encontrado."},
                            status_code=404)
    url = f"http://{_ip_rede_local()}:8000/api/convert/download/{quote(caminho.name)}"
    try:
        from io import BytesIO
        import qrcode
        img = qrcode.make(url, box_size=9, border=2)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    except Exception as e:
        return JSONResponse({"ok": False, "erro": f"QR indisponível: {e}"},
                            status_code=500)


def _e_checkpoint(nome: str) -> bool:
    """True se o arquivo é um checkpoint/backup (não pode virar GGUF)."""
    n = nome.lower()
    return "checkpoint" in n or "backup" in n or n.endswith((".bak", ".backup"))

# Os 3 tipos mais usados (mesmos do dropdown da página de treino)
TIPOS_RAPIDOS = [
    {"quant": "Q4_K_M", "desc": "Recomendado — bom equilíbrio (≈50 MB)"},
    {"quant": "Q8_0", "desc": "Mais preciso (≈100 MB)"},
    {"quant": "F16", "desc": "Precisão total (≈200 MB)"},
]


def _matar_processos_com_arquivo(nome: str):
    """Mata processos Windows que estão com o arquivo GGUF aberto (ex.: Ollama)."""
    try:
        cmd = (
            "powershell -NoProfile -Command "
            f"\"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{nome}*' }} "
            "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\""
        )
        subprocess.run(cmd, capture_output=True, timeout=30)
    except Exception:
        pass


def _apagar_gguf(nome: str) -> dict:
    """Apaga um GGUF, liberando antes o modelo no Ollama e matando processos em uso."""
    caminho = GGUF_DIR / nome
    if not caminho.exists():
        return {"ok": False, "erro": f"GGUF '{nome}' não encontrado em gguf/"}
    # Libera o modelo no Ollama (se registrado) para o arquivo não ficar em uso
    try:
        subprocess.run(["ollama", "rm", "rigelslm"], capture_output=True, timeout=30)
    except Exception:
        pass
    try:
        caminho.unlink()
    except PermissionError:
        _matar_processos_com_arquivo(nome)
        try:
            caminho.unlink()
        except Exception as e:
            return {"ok": False, "erro": f"GGUF em uso e não pôde ser liberado: {e}"}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
    return {"ok": True, "nome": nome}


class ConvertRequest(BaseModel):
    modelo: str = "modelo_melhor.pt"
    quantizacao: str = "Q4_K"


@router.get("/status")
async def convert_status():
    """Status dos modelos e conversões disponíveis."""
    modelos = []
    for path in sorted(MODEL_DIR.glob("*.pt"), key=lambda x: x.stat().st_mtime, reverse=True):
        nome = path.name
        modelos.append({
            "nome": nome,
            "tamanho_mb": round(path.stat().st_size / (1024 * 1024), 1),
            "data": datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
            "descricao": DESCRICOES_MODELOS.get(nome, ""),
            "recomendado": nome in RECOMENDADOS_MODELOS,
            "conversivel": not _e_checkpoint(nome),
        })

    # Verifica GGUF já convertidos
    ggufs = []
    if GGUF_DIR.exists():
        for f in GGUF_DIR.glob("*.gguf"):
            ggufs.append({
                "nome": f.name,
                "tamanho_mb": round(f.stat().st_size / (1024 * 1024), 1),
                "url": f"/api/convert/download/{quote(f.name)}",
            })

    return {
        "modelos_disponiveis": modelos,
        "ggufs_existentes": ggufs,
        "pode_converter": len(modelos) > 0,
        "modelo_path": str(MODEL_DIR.resolve()),
        "projeto_path": str(BASE_DIR.resolve()),
        "pasta_gguf": str(GGUF_DIR.resolve()),
        "tipos_rapidos": TIPOS_RAPIDOS,
        "ip_rede": _ip_rede_local(),
        "porta": 8000,
        "url_base": f"http://{_ip_rede_local()}:8000",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/progress")
async def conversion_progress():
    """Retorna o progresso atual da conversão."""
    state = get_conversion_state()
    return {
        "running": state["running"],
        "status": state["status"],
        "progress_pct": state["progress_pct"],
        "stage": state["stage"],
        "message": state["message"],
        "start_time": state["start_time"],
        "end_time": state["end_time"],
        "exit_code": state["exit_code"],
        "log_lines": state["log_lines"][-50:],  # últimas 50 linhas
        "modelo": state["modelo"],
        "quantizacao": state["quantizacao"],
        "gguf_path": state["gguf_path"],
        "tamanho_mb": state["tamanho_mb"],
    }


@router.get("/ollama-progress")
async def ollama_progress():
    """Retorna o progresso da criação do modelo Ollama."""
    state = get_ollama_state()
    return {
        "running": state["running"],
        "status": state["status"],
        "start_time": state["start_time"],
        "end_time": state["end_time"],
        "exit_code": state["exit_code"],
        "log_lines": state["log_lines"][-30:],
        "last_create": state["last_create"],
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
    if _e_checkpoint(modelo):
        return JSONResponse(
            status_code=400,
            content={"status": "error",
                     "message": "Checkpoint não pode ser convertido — use modelo.pt ou modelo_melhor.pt."}
        )

    # Verifica se já está convertendo
    current = get_conversion_state()
    if current["running"]:
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": "Já existe uma conversão em andamento"}
        )

    # Sobrescreve: apaga o GGUF de destino anterior (não acumula versões velhas)
    GGUF_DIR.mkdir(exist_ok=True)
    destino_gguf = GGUF_DIR / f"rigelslm_{quantizacao}.gguf"
    if destino_gguf.exists():
        _apagar_gguf(destino_gguf.name)

    cmd = [
        "python", "converter_para_gguf.py",
        "--model", str(modelo_path),
        "--quant", quantizacao
    ]

    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "dashboard.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Iniciando conversão: {' '.join(cmd)}\n")

    log_path = LOGS_DIR / "conversao.log"

    # Usa o runner com progresso em vez do stream simples
    background_tasks.add_task(
        run_conversion_with_progress, cmd, BASE_DIR, log_path, modelo, quantizacao
    )

    return {
        "status": "started",
        "message": f"Conversão de {modelo} para GGUF ({quantizacao}) iniciada",
        "timestamp": datetime.now().isoformat()
    }


@router.delete("/gguf")
async def apagar_gguf(nome: str = ""):
    """Apaga UM arquivo GGUF (libera do Ollama antes)."""
    nome = (nome or "").strip()
    if not nome or ".." in nome or "/" in nome or "\\" in nome:
        return JSONResponse(status_code=400, content={"ok": False, "erro": "nome inválido"})
    return _apagar_gguf(nome)


@router.delete("/gguf/todos")
async def apagar_todos_gguf():
    """Apaga TODOS os arquivos GGUF de gguf/ (um a um, liberando do Ollama)."""
    apagados = []
    erros = []
    if GGUF_DIR.exists():
        for f in sorted(GGUF_DIR.glob("*.gguf")):
            r = _apagar_gguf(f.name)
            (apagados if r.get("ok") else erros).append(f.name)
    return {"ok": True, "apagados": apagados, "erros": erros}


@router.post("/criar-ollama")
async def criar_modelo_ollama(background_tasks: BackgroundTasks):
    """Cria um modelo Ollama a partir do GGUF (rigelslm_Q4_K.gguf)."""
    # Procura qualquer GGUF disponível
    gguf_dir = BASE_DIR / "gguf"
    gguf_files = list(gguf_dir.glob("*.gguf"))
    if not gguf_files:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Nenhum arquivo GGUF encontrado em gguf/"})

    # Usa o primeiro GGUF encontrado (ou tenta rigelslm_Q4_K.gguf primeiro)
    gguf_path = gguf_dir / "rigelslm_Q4_K.gguf"
    if not gguf_path.exists():
        gguf_path = gguf_files[0]

    # Verifica se já está criando
    current_ollama = get_ollama_state()
    if current_ollama["running"]:
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": "Já existe uma criação Ollama em andamento"}
        )

    # IMPORTANTE: num_ctx no Modelfile. Sem ele o Ollama usa o context_length
    # do GGUF (512) e o chat estoura o contexto (erro 400 exceed_context_size).
    modelfile_content = (
        f"FROM {gguf_path}\n\n"
        "PARAMETER num_ctx 2048\n"
        "PARAMETER temperature 0.7\n"
        "PARAMETER top_p 0.9\n"
        "PARAMETER num_predict 256\n"
    )
    modelfile_path = BASE_DIR / "gguf" / "Modelfile"
    modelfile_path.write_text(modelfile_content, encoding="utf-8")

    cmd = ["ollama", "create", "rigelslm", "-f", str(modelfile_path)]

    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "dashboard.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Criando modelo Ollama: {' '.join(cmd)}\n")

    log_path = LOGS_DIR / "ollama_create.log"

    # Usa o runner com progresso
    background_tasks.add_task(
        run_ollama_create_with_progress, cmd, BASE_DIR, log_path
    )

    return {
        "status": "started",
        "message": f"Criação do modelo Ollama 'rigelslm' iniciada a partir de {gguf_path.name}",
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
