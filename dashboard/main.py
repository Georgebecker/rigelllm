#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
main.py - App FastAPI principal do Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
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
import platform
import random
from jinja2 import Environment, FileSystemLoader
from contextlib import asynccontextmanager

# ============================================================================
# CRIA A APLICAÇÃO
# ============================================================================

@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Limpa processos órfãos do llama.cpp (porta 8080) antes de subir
    try:
        from dashboard.routes.chat import matar_llama_server_orfao
        mortos = matar_llama_server_orfao()
        if mortos:
            print(f"[STARTUP] Removidos {mortos} llama-server órfão(s) (porta 8080)")
    except Exception:
        pass
    yield


app = FastAPI(title="RigelSLM Dashboard", lifespan=_lifespan)

# ============================================================================
# CONFIGURA DIRETÓRIOS
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "dashboard" / "templates"
STATIC_DIR = BASE_DIR / "dashboard" / "static"
IMAGES_DIR = BASE_DIR / "images"
LOGS_DIR = BASE_DIR / "logs"
_JINJA_ENV = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

# ── Guardião de cabeçalhos (oculto + criptografado) ────────────────────
# Garante o cabeçalho oficial em README.md e INSTALL.md sempre que o
# dashboard inicia (execução implícita, silenciosa).
def _rodar_guardiao() -> None:
    try:
        _g = BASE_DIR / ".rigel_guard.py"
        if _g.exists():
            exec(compile(_g.read_text(encoding="utf-8"), str(_g), "exec"),
                 {"__file__": str(_g), "__name__": "__rigel_guard__"})
    except Exception:
        pass


_rodar_guardiao()

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# LOG DE REQUISIÇÕES — visibilidade real (regra de ouro: "o usuário precisa
# ver o que acontece"). Registra TODOS os erros (com a exceção real, nunca
# "failed to fetch" sem causa) e todas as chamadas /api (status + tempo).
# ============================================================================
@app.middleware("http")
async def _log_requisicoes(request: Request, call_next):
    import time as _time
    t0 = _time.time()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception as e:
        try:
            with open(LOGS_DIR / "requests.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] ERRO {request.method} "
                        f"{request.url.path} {type(e).__name__}: {e}\n")
        except Exception:
            pass
        raise
    dt = round((_time.time() - t0) * 1000)
    if status >= 400 or request.url.path.startswith("/api"):
        try:
            with open(LOGS_DIR / "requests.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] {status} {request.method} "
                        f"{request.url.path} ({dt}ms)\n")
        except Exception:
            pass
    return response

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
    from .routes import train, chat, rss, convert, generate, logs, diagnostico, ollama, debate
    from .routes import debate_local, topicos, datasets, treino_local, treino_colab
    from .routes import executor, scrap
    from .routes import tratamento
    from .routes import deploy
    from .routes import celular
    from .routes import convert_txt
    from .routes import dados
    from .services import monitor
    from dashboard.services.limpeza import limpar_ansi
    app.include_router(train.router)
    app.include_router(chat.router)
    app.include_router(rss.router)
    app.include_router(convert.router)
    app.include_router(generate.router)
    app.include_router(logs.router)
    app.include_router(diagnostico.router)
    app.include_router(ollama.router)
    app.include_router(debate.router)
    app.include_router(debate_local.router)
    app.include_router(topicos.router)
    app.include_router(datasets.router)
    app.include_router(treino_local.router)
    app.include_router(treino_colab.router)
    app.include_router(executor.router)
    app.include_router(scrap.router)
    app.include_router(tratamento.router)
    app.include_router(deploy.router)
    app.include_router(celular.router)
    app.include_router(convert_txt.router)
    app.include_router(dados.router)
except ImportError as e:
    print(f"⚠️ Alguns routers não puderam ser carregados: {e}")

# ============================================================================
# CACHE DE SISTEMA (evita chamadas lentas repetidas)
# ============================================================================
MODEL_PATH = BASE_DIR / "modelo" / "modelo_melhor.pt"
_cache = {"file_count": 0, "file_count_time": 0, "full_status": {}, "full_status_time": 0}

def _contar_arquivos_rapido(caminho):
    """Conta .txt usando os.listdir (mais rápido que glob no Windows)."""
    try:
        return sum(1 for f in os.listdir(caminho) if f.endswith('.txt'))
    except:
        return 0

def _contar_arquivos_lento():
    """Contagem de arquivos com cache de 300s (5 min). Usa os.listdir para velocidade."""
    now = datetime.now().timestamp()
    if now - _cache["file_count_time"] <= 300:
        return _cache["file_count"]
    processed_dir = BASE_DIR / "dados" / "processed"
    total = 0
    if processed_dir.exists():
        try:
            # Apenas arquivos .txt diretos (os.listdir é ~10x mais rápido que glob)
            total = _contar_arquivos_rapido(processed_dir)
            # Subpastas apenas primeiro nível
            for item in os.listdir(processed_dir):
                sub = processed_dir / item
                if sub.is_dir():
                    total += _contar_arquivos_rapido(sub)
        except:
            pass
    _cache["file_count"] = total
    _cache["file_count_time"] = now
    return total

async def get_system_status():
    """Status resumido com cache de 60s para contagem de arquivos."""
    now_dt = datetime.now()
    total_files = await asyncio.to_thread(_contar_arquivos_lento)
    cpu_pct = await asyncio.to_thread(lambda: psutil.cpu_percent(interval=0.1))
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
# FUNÇÃO PARA DADOS DETALHADOS DO SISTEMA (com cache de 10s)
# ============================================================================
def get_full_status():
    global _cache
    now = datetime.now().timestamp()
    if now - _cache["full_status_time"] <= 10:
        return _cache["full_status"]

    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_freq = psutil.cpu_freq()
    cpu_cores = psutil.cpu_count(logical=True)
    cpu_per_core = psutil.cpu_percent(interval=0.05, percpu=True)
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
    total_arquivos = _contar_arquivos_lento()

    # 🔍 Info do MODELO + TREINO (página inicial sempre atualizada com o treino)
    modelo_info = {}
    try:
        _m = Path("modelo/modelo_melhor.pt")
        modelo_info["nome"] = "modelo_melhor.pt"
        modelo_info["existe"] = _m.exists()
        if _m.exists():
            modelo_info["data"] = datetime.fromtimestamp(_m.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            modelo_info["tamanho_mb"] = round(_m.stat().st_size / 1e6, 1)
        _ck = Path("modelo/checkpoint_jsonl.pt")
        if _ck.exists():
            modelo_info["checkpoint"] = {
                "nome": "checkpoint_jsonl.pt",
                "data": datetime.fromtimestamp(_ck.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "tamanho_mb": round(_ck.stat().st_size / 1e6, 1),
            }
        _ck2 = Path("modelo/checkpoint.pt")
        if _ck2.exists():
            modelo_info["checkpoint_base"] = {
                "nome": "checkpoint.pt",
                "data": datetime.fromtimestamp(_ck2.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
            }
    except Exception:
        pass

    treino_info = {}
    try:
        from dashboard.services import treino_local as _tl
        _e = _tl.get_estado()
        treino_info = {
            "rodando": bool(_e.get("rodando")),
            "etapa": _e.get("etapa"),
            "dataset": _e.get("dataset"),
            "mensagem": (_e.get("mensagem") or "")[:200],
            "inicio": _e.get("inicio"),
            "fim": _e.get("fim"),
            "progresso": _e.get("progresso"),
        }
    except Exception:
        pass

    # Métricas de treino (SFT jsonl tem prioridade; senão o txt)
    historico_metricas = []
    try:
        _mj = Path("logs/metricas_jsonl.json")
        if _mj.exists():
            _d = json.loads(_mj.read_text(encoding="utf-8"))
            historico_metricas = (_d.get("historico") or [])[-10:]
            for _mm in historico_metricas:
                _mm.setdefault("fonte", "jsonl")
    except Exception:
        pass
    if not historico_metricas:
        try:
            _mt = Path("logs/metricas.json")
            if _mt.exists():
                _d = json.loads(_mt.read_text(encoding="utf-8"))
                historico_metricas = (_d.get("historico") or [])[-10:]
                for _mm in historico_metricas:
                    _mm.setdefault("fonte", "txt")
        except Exception:
            pass

    # 🧠 Maturidade do modelo (mesma lógica do chat.py: calcular_barra_maturidade)
    # best_val_loss: prioridade do estado do treinador SFT, senão min do histórico.
    maturidade = None
    try:
        _best = None
        for _mm in historico_metricas:
            _v = _mm.get("val_loss")
            if _v is not None and (_best is None or _v < _best[0]):
                _best = (_v, _mm.get("epoch"))
        for _nome in ("modelo/estado_treino_jsonl.json", "modelo/estado_treino.json"):
            _ep = Path(_nome)
            if _ep.exists():
                _d = json.loads(_ep.read_text(encoding="utf-8"))
                _bv = _d.get("best_val_loss") if isinstance(_d, dict) else None
                if _bv is not None:
                    _best = (_bv, _d.get("epoch"))
                break
        if _best:
            _loss, _epoca = _best
            # loss <= 0.5 → 100% · loss >= 10 → 5% · interpolação linear no meio
            if _loss <= 0.5:
                _pct = 1.0
            elif _loss >= 10.0:
                _pct = 0.05
            else:
                _pct = max(0.05, min(1.0, 1.0 - (_loss - 0.5) / 9.5))
            maturidade = {
                "percentual": round(_pct * 100),
                "loss": round(_loss, 4),
                "epoca": _epoca,
            }
    except Exception:
        pass

    result = {
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
        "gguf_exists": modelo_gguf,
        "modelo_path": str(BASE_DIR / "modelo"),
        "projeto_path": str(BASE_DIR),
        "cpu_name": platform.processor(),
        "disk_type": "SSD" if psutil.disk_io_counters() else "HDD",
        "modelo_info": modelo_info,
        "treino_info": treino_info,
        "metricas": historico_metricas,
        "maturidade": maturidade,
    }

    _cache["full_status"] = result
    _cache["full_status_time"] = now
    return result

# ============================================================================
# ROTAS HTML (Múltiplas Páginas Independentes)
# ============================================================================
def _serve_html(nome: str) -> HTMLResponse:
    """Renderiza um template Jinja2 e retorna como resposta HTML."""
    try:
        template = _JINJA_ENV.get_template(nome)
        html = template.render()
        return HTMLResponse(content=html)
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Erro ao renderizar {nome}</h1><pre>{e}</pre>",
            status_code=500
        )

@app.get("/", response_class=HTMLResponse)
async def home():
    return _serve_html("index.html")

@app.get("/treinamento", response_class=HTMLResponse)
async def treinamento():
    return _serve_html("treinamento.html")

@app.get("/converter_txt", response_class=HTMLResponse)
async def converter_txt():
    return _serve_html("converter_txt.html")

@app.get("/chat", response_class=HTMLResponse)
async def chat():
    return _serve_html("chat.html")

@app.get("/rss", response_class=HTMLResponse)
async def rss():
    return _serve_html("rss.html")

@app.get("/converter", response_class=HTMLResponse)
async def converter():
    return _serve_html("converter.html")

@app.get("/gerar_dados", response_class=HTMLResponse)
async def gerar_dados():
    return _serve_html("gerar_dados.html")

@app.get("/gerar_local", response_class=HTMLResponse)
async def gerar_local():
    return _serve_html("gerar_local.html")

@app.get("/logs", response_class=HTMLResponse)
async def logs():
    return _serve_html("logs.html")

@app.get("/debate", response_class=HTMLResponse)
async def debate_page():
    return _serve_html("debate.html")

@app.get("/debate_local", response_class=HTMLResponse)
async def debate_local_page():
    return _serve_html("debate_local.html")

@app.get("/datasets", response_class=HTMLResponse)
async def datasets_page():
    return _serve_html("datasets.html")

@app.get("/treino_local", response_class=HTMLResponse)
async def treino_local_page():
    return _serve_html("treino_local.html")

@app.get("/treino_colab", response_class=HTMLResponse)
async def treino_colab_page():
    return _serve_html("treino_colab.html")

@app.get("/executor", response_class=HTMLResponse)
async def executor_page():
    return _serve_html("executor.html")

@app.get("/scrap", response_class=HTMLResponse)
async def scrap_page():
    return _serve_html("scrap.html")

@app.get("/tratamento", response_class=HTMLResponse)
async def tratamento_page():
    return _serve_html("tratamento.html")

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

# Listas para randomização quando quantidade > 1
_TEMPLATES_IDS = ["dialogo_curto", "artigo", "resumo", "poema", "carta",
                   "entrevista", "relatorio", "ensaio", "conto", "debate"]
_ESTILOS_IDS = ["neutro", "profissional", "professor", "especialista",
                 "casual_jovem", "humoristico", "poetico", "informativo_jornalistico"]


@app.post("/api/local-generate/gerar")
async def local_gerar(request: Request):
    """
    Gera conteúdo usando o modelo Ollama via subprocess.
    Aceita quantidade > 1 para gerar múltiplos itens com template/estilo aleatórios.
    
    Espera JSON: { template_id, tema, modelo, estilo, quantidade }
    """
    try:
        data = await request.json()
        template_id = data.get("template_id", "dialogo_curto")
        tema = data.get("tema", "")
        modelo = data.get("modelo", "llama3.2:1b")
        estilo = data.get("estilo", "neutro")
        quantidade = int(data.get("quantidade", 1))

        if not tema:
            return JSONResponse({"erro": "Tema é obrigatório"}, status_code=400)

        # Verifica se o Ollama está online
        if not verificar_ollama_online():
            return JSONResponse({"erro": "Ollama não está em execução. Inicie com 'ollama serve'"}, status_code=503)

        # Templates disponíveis
        templates_map = {
            "dialogo_curto": lambda t, e: f"Crie um diálogo curto entre duas pessoas sobre: {t}. Estilo: {e}.",
            "artigo": lambda t, e: f"Escreva um artigo jornalístico sobre: {t}. Estilo: {e}.",
            "resumo": lambda t, e: f"Faça um resumo conciso sobre: {t}. Estilo: {e}.",
            "poema": lambda t, e: f"Escreva um poema sobre: {t}. Estilo: {e}.",
            "carta": lambda t, e: f"Escreva uma carta pessoal sobre: {t}. Estilo: {e}.",
            "entrevista": lambda t, e: f"Crie uma entrevista fictícia sobre: {t}. Estilo: {e}.",
            "relatorio": lambda t, e: f"Elabore um relatório técnico sobre: {t}. Estilo: {e}.",
            "ensaio": lambda t, e: f"Escreva um ensaio reflexivo sobre: {t}. Estilo: {e}.",
            "conto": lambda t, e: f"Crie um conto fictício sobre: {t}. Estilo: {e}.",
            "debate": lambda t, e: f"Apresente um debate sobre: {t}. Estilo: {e}.",
        }

        pasta_local = BASE_DIR / "dados" / "gerados" / "gerados_local"
        pasta_local.mkdir(parents=True, exist_ok=True)

        resultados = []
        arquivos_gerados = []
        timestamp_base = datetime.now().strftime("%Y%m%d_%H%M%S")

        for i in range(quantidade):
            # Se quantidade > 1, randomiza template e estilo
            if quantidade > 1:
                tid = random.choice(_TEMPLATES_IDS)
                eid = random.choice(_ESTILOS_IDS)
            else:
                tid = template_id
                eid = estilo

            # Se o template não existe, fallback
            if tid not in templates_map:
                tid = "dialogo_curto"

            prompt = templates_map[tid](tema, eid)

            # Chama o Ollama via subprocess
            cmd = ["ollama", "run", modelo, prompt]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300  # 5 min para múltiplos itens
            )

            if proc.returncode != 0:
                # Se falhou no primeiro item, retorna erro
                if i == 0:
                    return JSONResponse({"erro": f"Ollama falhou: {proc.stderr[:200]}"}, status_code=500)
                # Se falhou em item subsequente, ignora e continua
                continue

            resultado = proc.stdout.strip()
            resultado = limpar_ansi(resultado)

            if not resultado or len(resultado) < 10:
                continue  # ignora resultados vazios

            resultados.append(resultado)

            # Salva cada item em arquivo separado
            nome_arquivo = f"local_{tid}_{timestamp_base}_{i+1}.txt"
            caminho_completo = pasta_local / nome_arquivo
            with open(caminho_completo, "w", encoding="utf-8") as f:
                f.write(resultado)

            arquivos_gerados.append({
                "nome": nome_arquivo,
                "caminho": str(caminho_completo),
                "tamanho_kb": round(len(resultado) / 1024, 1),
                "template": tid,
                "estilo": eid,
            })

        if not resultados:
            return JSONResponse({"erro": "Nenhum conteúdo foi gerado. Verifique se o Ollama está respondendo."}, status_code=500)

        return {
            "texto": resultados[0] if len(resultados) == 1 else "\n\n---\n\n".join(resultados),
            "conteudo": resultados[0] if len(resultados) == 1 else "\n\n---\n\n".join(resultados),
            "modelo": modelo,
            "template": template_id if quantidade == 1 else "multi",
            "quantidade_gerada": len(resultados),
            "quantidade_solicitada": quantidade,
            "arquivos": arquivos_gerados,
            "total_arquivos": len(arquivos_gerados),
        }

    except subprocess.TimeoutExpired:
        return JSONResponse({"erro": "Tempo limite excedido (300s). Tente com quantidade menor ou um modelo mais rápido."}, status_code=504)
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