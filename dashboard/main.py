import asyncio
import psutil
import subprocess
import json
import os
import socket
import shutil
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# ============================================================================
# CRIA A APLICAÇÃO
# ============================================================================
app = FastAPI(title="RigelSLM Dashboard")

# ============================================================================
# CONFIGURA DIRETÓRIOS
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "dashboard" / "templates"
STATIC_DIR = BASE_DIR / "dashboard" / "static"
IMAGES_DIR = BASE_DIR / "images"
LOGS_DIR = BASE_DIR / "logs"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

# ============================================================================
# ROUTERS (mantidos para compatibilidade, mas as rotas principais estão aqui)
# ============================================================================
try:
    from .routes.organizar import router as organizar_router
    app.include_router(organizar_router)
except ImportError:
    pass

try:
    from .routes import train, chat, rss, convert, generate, logs, diagnostico, ollama
    from .services import monitor
    app.include_router(train.router)
    app.include_router(chat.router)
    app.include_router(rss.router)
    app.include_router(convert.router)
    app.include_router(generate.router)
    app.include_router(logs.router)
    app.include_router(diagnostico.router)
    app.include_router(ollama.router)
except ImportError as e:
    print(f"⚠️ Alguns routers não puderam ser carregados: {e}")

# ============================================================================
# FUNÇÃO DE STATUS (para API /api/status)
# ============================================================================
MODEL_PATH = BASE_DIR / "modelo" / "modelo_melhor.pt"
_file_count_cache = {"count": 0, "time": 0}

async def get_system_status():
    global _file_count_cache
    now_dt = datetime.now()
    now_ts = now_dt.timestamp()
    if now_ts - _file_count_cache["time"] > 60:
        processed_dir = BASE_DIR / "dados" / "processed"
        total = 0
        if processed_dir.exists():
            for item in processed_dir.iterdir():
                if item.is_dir():
                    try:
                        total += len(list(item.iterdir()))
                    except:
                        pass
        _file_count_cache = {"count": total, "time": now_ts}
    total_files = _file_count_cache["count"]
    cpu_pct = await asyncio.to_thread(lambda: psutil.cpu_percent(interval=0.3))
    mem_pct = await asyncio.to_thread(lambda: psutil.virtual_memory().percent)
    disk_pct = await asyncio.to_thread(lambda: psutil.disk_usage('/').percent)
    return {
        "cpu": cpu_pct,
        "memory": mem_pct,
        "disk": disk_pct,
        "model_exists": MODEL_PATH.exists(),
        "model_date": datetime.fromtimestamp(MODEL_PATH.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if MODEL_PATH.exists() else None,
        "processed_files": total_files,
        "timestamp": now_dt.strftime("%d/%m/%Y %H:%M:%S")
    }

# ============================================================================
# FUNÇÃO PARA DADOS DETALHADOS DO SISTEMA
# ============================================================================
def get_full_status():
    cpu_percent = psutil.cpu_percent(interval=0.3)
    cpu_freq = psutil.cpu_freq()
    cpu_cores = psutil.cpu_count(logical=True)
    cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
    mem = psutil.virtual_memory()
    mem_total_gb = mem.total / (1024**3)
    mem_used_gb = mem.used / (1024**3)
    mem_percent = mem.percent
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    disk_io = psutil.disk_io_counters()
    if disk_io:
        read_mb = disk_io.read_bytes / (1024**2)
        write_mb = disk_io.write_bytes / (1024**2)
    else:
        read_mb = 0
        write_mb = 0
    modelo_melhor = Path("modelo/modelo_melhor.pt").exists()
    modelo_gguf = any(Path("gguf").glob("*.gguf")) if Path("gguf").exists() else False
    processed_dir = Path("dados/processed")
    if processed_dir.exists():
        total_arquivos = sum(1 for _ in processed_dir.glob("**/*.txt"))
    else:
        total_arquivos = 0

    return {
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
        "timestamp": datetime.now().isoformat(),
        "gguf_exists": modelo_gguf
    }

# ============================================================================
# ROTA PRINCIPAL - LÊ O HTML DIRETAMENTE
# ============================================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    index_path = TEMPLATES_DIR / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            conteudo = f.read()
        return HTMLResponse(content=conteudo)
    else:
        return HTMLResponse(
            content="<h1>index.html não encontrado</h1><p>Coloque o arquivo em dashboard/templates/</p>",
            status_code=404
        )

# ============================================================================
# APIS DO SISTEMA
# ============================================================================
@app.get("/api/status")
async def api_status():
    return await get_system_status()

@app.get("/api/system/details")
async def system_details():
    return get_full_status()

@app.get("/api/local-generate/pesquisa-status")
async def pesquisa_status():
    try:
        import duckduckgo_search
        disponivel = True
    except ImportError:
        disponivel = False
    return {"disponivel": disponivel}

# ============================================================================
# APIS DA ABA "GERAÇÃO LOCAL" (IMPLEMENTAÇÃO COMPLETA)
# ============================================================================

def verificar_ollama_online() -> bool:
    """Verifica se o Ollama está respondendo na porta 11434."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 11434))
        sock.close()
        return result == 0
    except:
        return False

def listar_modelos_ollama() -> List[str]:
    """Retorna a lista de modelos disponíveis no Ollama."""
    try:
        proc = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            encoding='cp1252',
            errors='ignore'
        )
        if proc.returncode == 0:
            linhas = proc.stdout.strip().split('\n')[1:]  # pula cabeçalho
            modelos = [linha.split()[0] for linha in linhas if linha.strip()]
            return modelos
        return []
    except:
        return []

@app.get("/api/local-generate/modelos")
async def local_modelos():
    """Retorna a lista de modelos do Ollama e status online."""
    online = verificar_ollama_online()
    modelos = listar_modelos_ollama() if online else []
    return {"online": online, "modelos": modelos}

@app.get("/api/local-generate/topicos")
async def local_topicos():
    """Retorna lista de tópicos lida do arquivo topicos.txt"""
    topicos_path = BASE_DIR / "topicos.txt"
    if topicos_path.exists():
        with open(topicos_path, "r", encoding="utf-8") as f:
            topicos = [linha.strip() for linha in f if linha.strip()]
        return {"topicos": topicos}
    else:
        # Fallback com tópicos padrão
        topicos = [
            "A Europa e a crise migratória",
            "A Grécia e a filosofia ocidental",
            "A Revolução Francesa mudou o mundo",
            "A Rússia e sua influência no leste",
            "A abolição da escravatura em 1888",
            "A agricultura em diferentes climas",
            "A inteligência artificial no século XXI",
            "O impacto das redes sociais na democracia",
            "A economia circular e sustentabilidade",
            "A medicina personalizada e genômica",
        ]
        return {"topicos": topicos}

@app.get("/api/local-generate/templates")
async def local_templates():
    """Retorna templates disponíveis para geração"""
    templates = [
        {"id": "dialogo_curto", "nome": "Diálogo Curto", "temperatura": 0.7, "max_tokens": 256, "descricao": "Gera um diálogo rápido entre duas pessoas."},
        {"id": "artigo", "nome": "Artigo", "temperatura": 0.8, "max_tokens": 1024, "descricao": "Gera um artigo completo sobre o tema."},
        {"id": "resumo", "nome": "Resumo", "temperatura": 0.5, "max_tokens": 200, "descricao": "Gera um resumo conciso do tema."},
        {"id": "poema", "nome": "Poema", "temperatura": 0.9, "max_tokens": 150, "descricao": "Gera um poema criativo."},
        {"id": "carta", "nome": "Carta", "temperatura": 0.7, "max_tokens": 300, "descricao": "Gera uma carta pessoal."},
        {"id": "entrevista", "nome": "Entrevista", "temperatura": 0.8, "max_tokens": 500, "descricao": "Gera uma entrevista fictícia."},
        {"id": "relatorio", "nome": "Relatório", "temperatura": 0.4, "max_tokens": 600, "descricao": "Gera um relatório técnico."},
        {"id": "ensaio", "nome": "Ensaio", "temperatura": 0.6, "max_tokens": 400, "descricao": "Gera um ensaio reflexivo."},
        {"id": "traducao", "nome": "Tradução", "temperatura": 0.3, "max_tokens": 300, "descricao": "Traduz o tema para outro idioma."},
        {"id": "conto", "nome": "Conto", "temperatura": 0.9, "max_tokens": 800, "descricao": "Gera um conto fictício."},
        {"id": "debate", "nome": "Debate", "temperatura": 0.7, "max_tokens": 500, "descricao": "Gera um debate entre dois pontos de vista."},
    ]
    return {"templates": templates}

@app.get("/api/local-generate/estilos")
async def local_estilos():
    """Retorna estilos de escrita disponíveis"""
    estilos = [
        {"id": "neutro", "nome": "Neutro (padrão)", "descricao": "Estilo padrão do template, sem modificações."},
        {"id": "profissional", "nome": "Profissional", "descricao": "Linguagem formal, técnica e corporativa."},
        {"id": "criativo", "nome": "Criativo", "descricao": "Linguagem poética e imaginativa."},
        {"id": "humoristico", "nome": "Humorístico", "descricao": "Tom leve e engraçado."},
        {"id": "dramatico", "nome": "Dramático", "descricao": "Linguagem intensa e emocional."},
        {"id": "cientifico", "nome": "Científico", "descricao": "Linguagem objetiva e baseada em fatos."},
        {"id": "conversacional", "nome": "Conversacional", "descricao": "Tom natural, como uma conversa informal."},
        {"id": "poetico", "nome": "Poético", "descricao": "Linguagem lírica e rítmica."},
    ]
    return {"estilos": estilos}

@app.post("/api/local-generate/gerar")
async def local_gerar(request: Request):
    """
    Gera conteúdo usando o modelo Ollama via subprocess.
    Espera JSON: { template_id, tema, modelo, estilo, idioma_destino, quantidade }
    """
    try:
        data = await request.json()
        template_id = data.get("template_id", "dialogo_curto")
        tema = data.get("tema", "")
        modelo = data.get("modelo", "llama3.2:1b")
        estilo = data.get("estilo", "neutro")
        idioma = data.get("idioma_destino", "inglês")
        quantidade = int(data.get("quantidade", 1))

        if not tema:
            return JSONResponse({"erro": "Tema é obrigatório"}, status_code=400)

        # Verifica se o Ollama está online
        if not verificar_ollama_online():
            return JSONResponse({"erro": "Ollama não está em execução. Inicie com 'ollama serve'"}, status_code=503)

        # Monta o prompt baseado no template
        templates_map = {
            "dialogo_curto": f"Crie um diálogo curto entre duas pessoas sobre: {tema}. Estilo: {estilo}.",
            "artigo": f"Escreva um artigo jornalístico sobre: {tema}. Estilo: {estilo}.",
            "resumo": f"Faça um resumo conciso sobre: {tema}. Estilo: {estilo}.",
            "poema": f"Escreva um poema sobre: {tema}. Estilo: {estilo}.",
            "carta": f"Escreva uma carta pessoal sobre: {tema}. Estilo: {estilo}.",
            "entrevista": f"Crie uma entrevista fictícia sobre: {tema}. Estilo: {estilo}.",
            "relatorio": f"Elabore um relatório técnico sobre: {tema}. Estilo: {estilo}.",
            "ensaio": f"Escreva um ensaio reflexivo sobre: {tema}. Estilo: {estilo}.",
            "traducao": f"Traduza o seguinte texto para {idioma}: {tema}.",
            "conto": f"Crie um conto fictício sobre: {tema}. Estilo: {estilo}.",
            "debate": f"Apresente um debate sobre: {tema}. Estilo: {estilo}.",
        }

        prompt = templates_map.get(template_id, f"Fale sobre: {tema}. Estilo: {estilo}.")

        # Chama o Ollama via subprocess
        cmd = ["ollama", "run", modelo, prompt]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=120
        )

        if proc.returncode != 0:
            return JSONResponse({"erro": f"Erro no Ollama: {proc.stderr}"}, status_code=500)

        resultado = proc.stdout.strip()
        return {"conteudo": resultado, "modelo": modelo, "template": template_id}

    except subprocess.TimeoutExpired:
        return JSONResponse({"erro": "Tempo limite excedido (120s)"}, status_code=504)
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/api/local-generate/arquivos-salvos")
async def local_arquivos_salvos():
    """Lista arquivos salvos em dados/gerados/gerados_local/"""
    pasta = BASE_DIR / "dados" / "gerados" / "gerados_local"
    arquivos = []
    if pasta.exists():
        for item in pasta.iterdir():
            if item.is_file() and item.suffix == '.txt':
                arquivos.append({
                    "nome": item.name,
                    "tamanho_kb": round(item.stat().st_size / 1024, 1),
                    "data": datetime.fromtimestamp(item.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                })
    return {"arquivos": sorted(arquivos, key=lambda x: x["data"], reverse=True)}

@app.post("/api/local-generate/salvar-texto")
async def local_salvar_texto(request: Request):
    """Salva um texto em dados/gerados/gerados_local/"""
    try:
        data = await request.json()
        nome = data.get("nome", f"texto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        conteudo = data.get("conteudo", "")
        pasta = data.get("pasta", "gerados_local")

        if not conteudo:
            return JSONResponse({"erro": "Conteúdo vazio"}, status_code=400)

        pasta_path = BASE_DIR / "dados" / "gerados" / pasta
        pasta_path.mkdir(parents=True, exist_ok=True)

        caminho = pasta_path / nome
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(conteudo)

        return {"mensagem": f"Arquivo salvo com sucesso: {nome}", "caminho": str(caminho)}
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/api/local-generate/arquivo-salvo/{nome}")
async def local_ler_arquivo(nome: str):
    """Lê o conteúdo de um arquivo salvo."""
    pasta = BASE_DIR / "dados" / "gerados" / "gerados_local"
    caminho = pasta / nome
    if not caminho.exists():
        return JSONResponse({"erro": "Arquivo não encontrado"}, status_code=404)
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = f.read()
        return {"conteudo": conteudo}
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)

# ============================================================================
# ROTA DE TESTE PARA OLLAMA (opcional)
# ============================================================================
@app.get("/api/ollama/test")
async def test_ollama():
    """Rota simples para testar se o Ollama responde."""
    online = verificar_ollama_online()
    modelos = listar_modelos_ollama() if online else []
    return {"online": online, "modelos": modelos, "versao": "1.0"}

# ============================================================================
# EXECUÇÃO DIRETA
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)