"""Rota de RSS - Processamento de feeds RSS/Atom/XML com resultados reais"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import subprocess, httpx, re, json, html as html_mod
from datetime import datetime
from dashboard.services.monitor import ler_ultimas_linhas, get_ultimas_linhas_log
from dashboard.services.runner import stream_subprocess_to_log

router = APIRouter(prefix="/api/rss", tags=["RSS"])

BASE_DIR = Path(__file__).parent.parent.parent
FEEDS_PATH = BASE_DIR / "feeds.txt"
PROCESSADOS_PATH = BASE_DIR / "processados.txt"
LOGS_DIR = BASE_DIR / "logs"
GERADOS_DIR = BASE_DIR / "dados" / "gerados"


class RssRequest(BaseModel):
    quantidade: int = 10
    feeds: list[str] | None = None


class RssTestRequest(BaseModel):
    url: str


class AddFeedRequest(BaseModel):
    url: str


# Cache de resultados
_resultado_cache = {"ultimo_processamento": None, "resultado": None}


def contar_pasta_rss(nome_pasta: str) -> int:
    """Conta arquivos .txt em uma pasta de saída do RSS."""
    p = GERADOS_DIR / nome_pasta
    if p.exists():
        return len(list(p.glob("*.txt")))
    return 0


def contar_descartados() -> int:
    p = GERADOS_DIR / "descartados"
    if p.exists():
        return len(list(p.glob("*.txt")))
    return 0


@router.get("/status")
async def rss_status():
    """Status com contagem REAL de arquivos gerados por categoria."""
    feeds_existem = FEEDS_PATH.exists()

    # Contagem real das pastas de saída
    saidas = {
        "curtos": contar_pasta_rss("curtos"),
        "longos": contar_pasta_rss("longos"),
        "completos": contar_pasta_rss("completos"),
        "resumidos": contar_pasta_rss("resumidos"),
        "descartados": contar_descartados(),
    }
    total_gerados = sum(saidas.values())

    # Lê últimas linhas do log do RSS para extrair estatísticas
    log_rss = GERADOS_DIR / "logs" / "rss.log"
    ultimo_log = ""
    if log_rss.exists():
        ultimo_log = ler_ultimas_linhas(log_rss, 30)

    # Lista feeds (máx 50)
    feeds = []
    if feeds_existem:
        with open(FEEDS_PATH, "r", encoding="utf-8") as f:
            feeds = [linha.strip() for linha in f.readlines()
                     if linha.strip() and not linha.strip().startswith("#")]

    return {
        "feeds_cadastrados": len(feeds),
        "feeds_lista": feeds[:50],
        "arquivos_gerados": saidas,
        "total_gerados": total_gerados,
        "ultimo_log": ultimo_log,
        "resultado_anterior": _resultado_cache.get("resultado"),
        "timestamp": datetime.now().isoformat()
    }


@router.post("/processar")
async def processar_rss(
    req: RssRequest,
    background_tasks: BackgroundTasks,
):
    """Inicia o processamento dos feeds RSS."""
    cmd = ["python", "rss_processor.py", "--quantidade", str(req.quantidade)]
    if req.feeds:
        cmd.extend(["--feeds", ",".join(req.feeds)])

    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "dashboard.log"
    ts = datetime.now().isoformat()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] RSS: {' '.join(cmd)}\n")

    log_path = LOGS_DIR / "rss.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)

    _resultado_cache["ultimo_processamento"] = ts
    _resultado_cache["resultado"] = {
        "status": "processando",
        "quantidade": req.quantidade,
        "timestamp": ts,
    }

    return {
        "status": "started",
        "message": f"Processando {req.quantidade} feeds em segundo plano",
        "timestamp": ts
    }


@router.get("/logs")
async def rss_logs():
    """Últimas 100 linhas do log do RSS."""
    return await get_ultimas_linhas_log("rss.log", 100)


async def _detectar_feed_url(url: str) -> dict:
    """Tenta detectar feeds RSS/Atom em uma URL.
    Retorna dict com status, feeds_encontrados, amostras, etc."""
    resultados = []
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as cli:
            resp = await cli.get(url, headers={"User-Agent": "RigelSLM-RSS/1.0"})
            if resp.status_code != 200:
                return {"status": "erro", "detalhe": f"HTTP {resp.status_code}"}
            content_type = resp.headers.get("content-type", "")
            texto = resp.text

            # Testa se já é RSS/Atom XML direto
            if "xml" in content_type.lower() or texto.strip().startswith("<?xml"):
                if "<rss" in texto[:500] or "<feed" in texto[:500]:
                    # É um feed direto
                    titulos = re.findall(r"<title[^>]*>(.*?)</title>", texto, re.IGNORECASE | re.DOTALL)[:5]
                    resultados.append({
                        "url": url,
                        "tipo": "feed_direto",
                        "titulos": [html_mod.unescape(t.strip()) for t in titulos if t.strip()][:5],
                    })
                    return {"status": "ok", "feeds": resultados, "fonte": url}

            # Procura por <link> tags com RSS/Atom
            # <link rel="alternate" type="application/rss+xml" href="...">
            # <link rel="alternate" type="application/atom+xml" href="...">
            padrao = re.compile(
                r'<link\s+[^>]*?(?:rel=["\']alternate["\'])[^>]*?(?:type=["\']application/(rss|atom)\+xml["\'])[^>]*?href=["\']([^"\']+)["\'][^>]*?>',
                re.IGNORECASE
            )
            for match in padrao.finditer(texto):
                tipo = match.group(1)
                href = match.group(2)
                feed_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                resultados.append({"url": feed_url, "tipo": f"{tipo}_link", "titulos": []})

            # Fallback: procura por links .rss, .xml, /feed/ no texto
            if not resultados:
                padrao2 = re.compile(
                    r'<a\s+[^>]*?href=["\']([^"\']*(?:rss|feed|atom|\.xml)[^"\']*)["\'][^>]*?>(.*?)</a>',
                    re.IGNORECASE
                )
                for match in padrao2.finditer(texto):
                    href = match.group(1)
                    feed_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                    resultados.append({"url": feed_url, "tipo": "link_suspeito", "titulos": []})

            # Se encontrou feeds, tenta parsear o primeiro para amostra
            if resultados:
                feed_amostra = resultados[0]["url"]
                try:
                    resp2 = await cli.get(feed_amostra, timeout=10)
                    if resp2.status_code == 200:
                        txt2 = resp2.text
                        titulos = re.findall(r"<title[^>]*>(.*?)</title>", txt2, re.IGNORECASE | re.DOTALL)[:5]
                        resultados[0]["titulos"] = [html_mod.unescape(t.strip()) for t in titulos if t.strip()]
                except Exception:
                    pass

            return {"status": "ok", "feeds": resultados, "fonte": url}

    except httpx.TimeoutException:
        return {"status": "erro", "detalhe": "Tempo limite excedido (15s)"}
    except httpx.ConnectError:
        return {"status": "erro", "detalhe": "Não foi possível conectar ao servidor"}
    except Exception as e:
        return {"status": "erro", "detalhe": str(e)[:200]}


@router.post("/testar")
async def testar_rss(req: RssTestRequest):
    """Testa uma URL para detectar feeds RSS/Atom."""
    if not req.url or len(req.url.strip()) < 4:
        return JSONResponse(status_code=400, content={"status": "erro", "detalhe": "URL inválida"})
    resultado = await _detectar_feed_url(req.url.strip())
    return resultado


@router.post("/adicionar-feed")
async def adicionar_feed(req: AddFeedRequest):
    """Adiciona uma URL de feed ao arquivo feeds.txt."""
    url = req.url.strip()
    if not url:
        return JSONResponse(status_code=400, content={"status": "erro", "detalhe": "URL vazia"})

    # Lê feeds existentes
    feeds_existentes = set()
    if FEEDS_PATH.exists():
        with open(FEEDS_PATH, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    feeds_existentes.add(linha)

    if url in feeds_existentes:
        return {"status": "ok", "mensagem": "Feed já existente na lista", "ja_existia": True}

    # Adiciona
    with open(FEEDS_PATH, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")

    # Log
    log_file = LOGS_DIR / "dashboard.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] RSS ADICIONADO: {url}\n")

    return {"status": "ok", "mensagem": "Feed adicionado à lista com sucesso"}
