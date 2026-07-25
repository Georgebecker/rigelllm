"""Rotas de Logs - Visualização e exportação de logs do sistema"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, JSONResponse
from pathlib import Path
from datetime import datetime
import os

router = APIRouter(prefix="/api/logs", tags=["Logs"])

BASE_DIR = Path(__file__).parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"


def listar_arquivos_log():
    """Lista todos os arquivos de log disponíveis."""
    arquivos = []
    if LOGS_DIR.exists():
        for f in sorted(LOGS_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix in (".log", ".json", ".txt"):
                tamanho = f.stat().st_size
                arquivos.append({
                    "nome": f.name,
                    "tamanho_kb": round(tamanho / 1024, 1),
                    "data": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                    "extensao": f.suffix
                })

    # Também busca logs em dados/gerados/logs/
    rss_log_dir = BASE_DIR / "dados" / "gerados" / "logs"
    if rss_log_dir.exists():
        for f in sorted(rss_log_dir.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file():
                arquivos.append({
                    "nome": f"rss_logs/{f.name}",
                    "tamanho_kb": round(f.stat().st_size / 1024, 1),
                    "data": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                    "extensao": f.suffix
                })

    return arquivos


@router.get("/listar")
async def listar_logs():
    """Lista todos os logs disponíveis."""
    return {"arquivos": listar_arquivos_log()}


@router.get("/visualizar/{nome_arquivo}")
async def visualizar_log(nome_arquivo: str):
    """Visualiza o conteúdo de um log específico."""
    # Tenta no diretório principal de logs
    caminho = LOGS_DIR / nome_arquivo
    if not caminho.exists():
        # Tenta no diretório de logs do RSS
        caminho = BASE_DIR / "dados" / "gerados" / "logs" / nome_arquivo

    if not caminho.exists():
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"Log {nome_arquivo} não encontrado"}
        )

    if caminho.suffix == ".json":
        try:
            conteudo = caminho.read_text(encoding="utf-8")
            return JSONResponse(content={"conteudo": conteudo[-5000:]})
        except Exception:
            return PlainTextResponse(f"Erro ao ler {nome_arquivo}", status_code=500)

    try:
        conteudo = caminho.read_text(encoding="utf-8", errors="replace")
    except UnicodeDecodeError:
        conteudo = caminho.read_text(encoding="latin-1", errors="replace")

    # Retorna as últimas 200 linhas
    linhas = conteudo.splitlines()
    ultimas = "\n".join(linhas[-200:])

    return PlainTextResponse(ultimas)


@router.get("/dashboard")
async def log_dashboard():
    """Últimas entradas do log do dashboard."""
    log_file = LOGS_DIR / "dashboard.log"
    if log_file.exists():
        conteudo = log_file.read_text(encoding="utf-8", errors="replace")
        linhas = conteudo.splitlines()
        return {"logs": "\n".join(linhas[-100:])}
    return {"logs": "Nenhum log do dashboard encontrado."}


@router.get("/metricas")
async def metricas_treino():
    """Métricas detalhadas de treino."""
    metricas_path = LOGS_DIR / "metricas.json"
    if metricas_path.exists():
        try:
            import json
            dados = json.loads(metricas_path.read_text(encoding="utf-8"))
            return dados
        except (json.JSONDecodeError, Exception):
            return {"historico": []}
    return {"historico": []}
