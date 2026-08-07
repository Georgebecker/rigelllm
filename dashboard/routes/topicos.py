#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
topicos.py - Gerenciamento de tópicos para geração de conteúdo
Versão: 1.0.0 | Data: 31/07/2026

Endpoints:
  GET  /api/topicos/listar      - Lista tópicos do topicos.txt
  POST /api/topicos/gerar       - Gera novos tópicos via RSS + DeepSeek (fallback)
  POST /api/topicos/sortear     - Retorna um tópico aleatório
  POST /api/topicos/rss         - Busca títulos de feeds RSS e adiciona como tópicos
"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pathlib import Path
import json
import random
import asyncio
import subprocess
from datetime import datetime

router = APIRouter(prefix="/api/topicos", tags=["Tópicos"])

BASE_DIR = Path(__file__).parent.parent.parent
TOPICOS_PATH = BASE_DIR / "topicos.txt"
FEEDS_PATH = BASE_DIR / "feeds.txt"
TOPICOS_PADRAO = [
    "Inteligência Artificial no Brasil",
    "Mudanças climáticas e seus impactos",
    "A história da filosofia ocidental",
    "Tecnologia e educação",
    "Saúde pública no século XXI",
    "Política brasileira contemporânea",
    "Arte e cultura digital",
    "Economia e globalização",
    "Ciência e inovação tecnológica",
    "Literatura brasileira moderna",
]


def _carregar_topicos() -> list:
    """Carrega tópicos do arquivo. Retorna lista padrão se não existir."""
    if not TOPICOS_PATH.exists():
        return TOPICOS_PADRAO
    try:
        with open(TOPICOS_PATH, "r", encoding="utf-8") as f:
            topicos = [linha.strip() for linha in f if linha.strip()]
        return topicos if topicos else TOPICOS_PADRAO
    except Exception:
        return TOPICOS_PADRAO


def _salvar_topicos(topicos: list):
    """Salva lista de tópicos no arquivo (evitando duplicatas)."""
    vistos = set()
    unicos = []
    for t in topicos:
        t_norm = t.strip().lower()
        if t_norm not in vistos and t.strip():
            vistos.add(t_norm)
            unicos.append(t.strip())
    TOPICOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOPICOS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(unicos) + "\n")


# ============================================================================
# Funções auxiliares para buscar tópicos de feeds RSS
# ============================================================================

async def _buscar_topicos_rss(limite: int = 20) -> list:
    """
    Busca títulos de notícias dos feeds RSS configurados em feeds.txt.
    Retorna uma lista de strings (títulos) sem duplicatas.
    Não depende de DeepSeek nem de API externa.
    """
    import httpx
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    # Lê os feeds
    if not FEEDS_PATH.exists():
        return []
    with open(FEEDS_PATH, "r", encoding="utf-8") as f:
        urls = [linha.strip() for linha in f if linha.strip() and not linha.startswith("#")]

    if not urls:
        return []

    # Seleciona alguns feeds aleatoriamente para não sobrecarregar
    random.shuffle(urls)
    urls = urls[:min(8, len(urls))]  # no máximo 8 feeds por vez

    titulos = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    async with httpx.AsyncClient(timeout=8.0, headers=headers, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                # Parse XML
                root = ET.fromstring(resp.text)
                # RSS 2.0: /rss/channel/item/title
                # Atom: /feed/entry/title
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    if title_el is not None and title_el.text:
                        titulos.append(title_el.text.strip())
                for entry in root.findall(".//atom:entry", ns):
                    title_el = entry.find("atom:title", ns)
                    if title_el is not None and title_el.text:
                        titulos.append(title_el.text.strip())
            except Exception:
                continue  # ignora feeds com erro

    # Remove duplicatas e limpa
    vistos = set()
    unicos = []
    for t in titulos:
        t_limpo = t.strip().strip('"').strip("'")
        if t_limpo and t_limpo.lower() not in vistos and len(t_limpo) > 10:
            vistos.add(t_limpo.lower())
            unicos.append(t_limpo)

    return unicos[:limite]


async def _gerar_topicos_deepseek(quantidade: int = 10) -> list:
    """
    Tenta gerar tópicos via DeepSeek. Se falhar, retorna lista vazia.
    """
    try:
        from config import client, MODEL_NAME, API_KEY
        if not API_KEY or API_KEY == "deepseek-aqui":
            return []
        
        # Timeout curto para não travar
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": f"""Gere {quantidade} tópicos variados em português brasileiro para geração de conteúdo textual.
Os tópicos devem cobrir áreas como: tecnologia, ciência, cultura, história, política, economia, saúde, educação, arte, esportes, meio ambiente.
Cada tópico deve ser uma frase curta (máximo 80 caracteres).
Retorne APENAS a lista, um tópico por linha, sem numeração."""}],
            max_tokens=500,
            temperature=0.8,
            timeout=15,
        ))
        texto = response.choices[0].message.content.strip()
        novos = [linha.strip().strip("-•*1234567890. ") for linha in texto.split("\n") if linha.strip()]
        return novos[:quantidade]
    except Exception:
        return []


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/listar")
async def listar_topicos():
    """Retorna a lista de tópicos disponíveis."""
    topicos = _carregar_topicos()
    return {
        "topicos": topicos,
        "total": len(topicos),
        "arquivo": str(TOPICOS_PATH),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/sortear")
async def sortear_topico():
    """Retorna um tópico aleatório da lista."""
    topicos = _carregar_topicos()
    if not topicos:
        return {"topico": "", "erro": "Nenhum tópico disponível"}
    return {"topico": random.choice(topicos)}


@router.post("/sortear")
async def sortear_topico_post():
    """Retorna um tópico aleatório da lista (POST)."""
    return await sortear_topico()


@router.post("/gerar")
async def gerar_topicos(background_tasks: BackgroundTasks, quantidade: int = 15):
    """
    Gera novos tópicos e adiciona ao topicos.txt.
    
    Estratégia (em ordem):
    1. Busca títulos de feeds RSS (notícias reais) — sempre funciona
    2. Se DeepSeek estiver configurado, complementa com tópicos gerados por IA
    3. Fallback: gera tópicos padrão
    
    Retorna IMEDIATAMENTE e processa RSS em background.
    """
    # 1. Tenta RSS primeiro (sempre disponível, não depende de API key)
    topicos_rss = []
    try:
        topicos_rss = await _buscar_topicos_rss(limite=quantidade)
    except Exception:
        pass

    # 2. Tenta DeepSeek (se configurado)
    topicos_deepseek = []
    try:
        topicos_deepseek = await _gerar_topicos_deepseek(quantidade=quantidade)
    except Exception:
        pass

    # 3. Fallback: tópicos variados manuais
    topicos_fallback = [
        "Brasil e a economia digital",
        "Inteligência Artificial na medicina",
        "Mudanças climáticas e agricultura",
        "Cibersegurança e privacidade",
        "Educação a distância pós-pandemia",
        "Energias renováveis no Brasil",
        "Democracia e redes sociais",
        "Saúde mental na era digital",
        " Mobilidade urbana sustentável",
        "Cultura de inovação nas empresas",
        "Desigualdade social e políticas públicas",
        "Exploração espacial e novas fronteiras",
        "Inteligência Artificial e ética",
        "Blockchain e criptomoedas",
        "Biodiversidade da Amazônia",
    ]

    # Combina as fontes
    topicos_existentes = _carregar_topicos()
    novos = []
    usou_rss = len(topicos_rss) > 0
    usou_deepseek = len(topicos_deepseek) > 0

    if topicos_rss:
        novos.extend(topicos_rss)
    if topicos_deepseek:
        novos.extend(topicos_deepseek)
    if not novos:
        novos = topicos_fallback[:quantidade]

    topicos_existentes.extend(novos)
    _salvar_topicos(topicos_existentes)

    # Dispara processamento RSS completo em background (para mais tópicos no futuro)
    background_tasks.add_task(_executar_rss_processor)

    fonte = "RSS (notícias)" if usou_rss else ("DeepSeek" if usou_deepseek else "fallback manual")
    return {
        "status": "ok",
        "mensagem": f"✅ {len(novos)} novos tópicos adicionados via {fonte}",
        "fonte": fonte,
        "novos": novos[:20],
        "total": len(topicos_existentes),
    }


@router.post("/rss")
async def topicos_via_rss(background_tasks: BackgroundTasks, quantidade: int = 20):
    """
    Busca títulos de feeds RSS e adiciona como tópicos.
    Processa em background e retorna imediatamente.
    """
    topicos = await _buscar_topicos_rss(limite=quantidade)
    if not topicos:
        return JSONResponse(
            status_code=504,
            content={"status": "erro", "mensagem": "Nenhum tópico encontrado nos feeds RSS. Os feeds podem estar offline."}
        )

    topicos_existentes = _carregar_topicos()
    topicos_existentes.extend(topicos)
    _salvar_topicos(topicos_existentes)

    # Dispara processamento RSS completo em background
    background_tasks.add_task(_executar_rss_processor)

    return {
        "status": "ok",
        "mensagem": f"✅ {len(topicos)} tópicos extraídos dos feeds RSS",
        "novos": topicos[:20],
        "total": len(topicos_existentes),
    }


def _executar_rss_processor():
    """
    Executa o rss_processor.py em background para enriquecer topicos.txt
    com títulos de notícias reais.
    """
    try:
        rss_script = BASE_DIR / "rss_processor.py"
        if rss_script.exists():
            subprocess.Popen(
                ["python", str(rss_script), "--quantidade", "10"],
                cwd=str(BASE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
    except Exception:
        pass
