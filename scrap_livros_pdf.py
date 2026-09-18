#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================================
# RIGELSLM - SCRAP DE LIVROS PDF (PORTUGUÊS DO BRASIL) v1.0.0
# Data: 09/08/2026
# ============================================================================
# O QUE FAZ
#   Lê a lista de sites em sites_pdfs.txt (um por linha; # = comentário) e,
#   para cada site, aplica um EXTRATOR específico com a MESMA metodologia de
#   verificação do baixelivros: TESTAR estrutura -> extrair links -> baixar ->
#   VALIDAR o arquivo. Sites sem extrator usam o genérico (links .pdf diretos).
#
# FORMATOS ACEITOS (por prioridade)
#   1. PDF (.pdf) .......................... salvo como .pdf
#   2. HTML "read online" (.html) .......... texto extraído -> .txt
#   3. HTML (zip) (.zip) ................... descompactado -> texto -> .txt
#   4. TXT (.txt) .......................... copiado como .txt
#   (EPUB / Kindle / MOBI são IGNORADOS - formatos fechados para outras
#    plataformas; o texto é difícil de extrair.)
#
# FILTRO DE IDIOMA (PT-BR)
#   Detecta se o texto é português do BRASIL ou de PORTUGAL (scoring de
#   palavras típicas). O que não for brasileiro vai para dados/descartados/livros/.
#
# Uso:
#   python scrap_livros_pdf.py                       # varre TODOS os sites
#   python scrap_livros_pdf.py --site baixelivros.com.br --limite 3
#   python scrap_livros_pdf.py --site gutenberg.org --limite 5
#   python scrap_livros_pdf.py --verificar           # só testa estrutura
# ============================================================================

import os
import re
import sys
import io
import time
import json
import shutil
import zipfile
import argparse
import tempfile
from datetime import datetime
from urllib.parse import urlparse, unquote, parse_qs
from typing import List, Optional, Tuple, Dict

import requests
from bs4 import BeautifulSoup

# Console UTF-8 (evita crash com emojis quando o stdout é pipe)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================================
# 1. CONFIGURAÇÃO
# ============================================================================
PROJETO_ROOT = os.path.dirname(os.path.abspath(__file__))
PASTA_RAIZ = os.path.join("dados", "raw", "livros")          # downloads válidos
PASTA_DESCARTES = os.path.join("dados", "descartados", "livros")  # não-PT-BR / inválidos
SITES_LISTA = "sites_pdfs.txt"
LOG_PATH = os.path.join("logs", "scrap_livros.log")
MANIFESTO_PATH = os.path.join(PASTA_RAIZ, "_manifesto.json")
LOGS_DIR = os.path.join("logs")
PROGRESSO_PATH = os.path.join(LOGS_DIR, "scrap_progresso.json")   # painel /pdfs lê
RELATORIO_PATH = os.path.join(LOGS_DIR, "scrap_relatorio.json")   # contadores por site
HASH_REGISTRY_PATH = os.path.join(LOGS_DIR, "scrap_hash_registry.json")  # dedup por conteúdo

os.makedirs(PASTA_RAIZ, exist_ok=True)
os.makedirs(PASTA_DESCARTES, exist_ok=True)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Bons cidadãos: pausa entre requisições (evita bloqueio por flood)
DELAY = float(os.getenv("SCRAP_DELAY", "1.2"))
TIMEOUT = float(os.getenv("SCRAP_TIMEOUT", "45"))
RETRIES = int(os.getenv("SCRAP_RETRIES", "2"))

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
}

# fitz (PyMuPDF) é OPCIONAL: usado só para extrair amostra de texto de PDF
# (filtro de idioma). Sem ele, PDFs passam sem filtro de idioma.
try:
    import fitz  # type: ignore
    FITZ_AVAILABLE = True
except Exception:
    fitz = None
    FITZ_AVAILABLE = False


def log(msg: str, nivel: str = "INFO") -> None:
    linha = f"[{datetime.now().strftime('%H:%M:%S')}] [{nivel}] {msg}"
    print(linha)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


# ============================================================================
# PROGRESSO EM TEMPO REAL (regra de ouro: o usuário precisa VER acontecendo)
# O painel /pdfs lê logs/scrap_progresso.json a cada poucos segundos.
# ============================================================================
PROGRESSO_ATUAL = {
    "site": "", "site_i": 0, "site_total": 0, "pct": 0, "atual": "",
    "ok": 0, "erro": 0, "pulados": 0, "dups": 0,
    "decorrido_s": 0, "fase": "iniciando", "msg": "",
    "atualizado": "",
    "_inicio": time.time(),
}


def _gravar_progresso() -> None:
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(PROGRESSO_PATH, "w", encoding="utf-8") as f:
            json.dump(PROGRESSO_ATUAL, f, ensure_ascii=False)
    except Exception:
        pass


def _atualizar_progresso(dom: str, atual: str, res: dict,
                         site_i: int = 0, site_total: int = 1,
                         fase: str = "baixando", msg: str = "") -> None:
    """Atualiza logs/scrap_progresso.json a cada item processado.
    pct = itens processados / links conhecidos até agora (progresso real)."""
    processados = (res.get("ok", 0) + res.get("erro", 0) +
                   res.get("pulados", 0) + res.get("dups", 0))
    total = res.get("links", 0) or 1
    pct = round(100.0 * min(processados, total) / total, 1) if total else 0.0
    if res.get("links", 0) and processados >= res.get("links", 0):
        pct = 100.0
    PROGRESSO_ATUAL.update({
        "site": dom, "site_i": site_i, "site_total": site_total,
        "pct": pct, "atual": atual, "fase": fase, "msg": msg,
        "ok": res.get("ok", 0), "erro": res.get("erro", 0),
        "pulados": res.get("pulados", 0), "dups": res.get("dups", 0),
        "decorrido_s": int(time.time() - PROGRESSO_ATUAL.get("_inicio", time.time())),
        "atualizado": datetime.now().isoformat(),
    })
    _gravar_progresso()


# ============================================================================
# DEDUP POR CONTEÚDO (hash SHA-1) — mesmo PDF baixado de 2 sites vira 1 só
# ============================================================================
def _carregar_hashes() -> dict:
    try:
        if os.path.exists(HASH_REGISTRY_PATH):
            with open(HASH_REGISTRY_PATH, encoding="utf-8") as f:
                dados = json.load(f)
                return dados if isinstance(dados, dict) else {}
    except Exception:
        pass
    return {}


def _salvar_hashes(reg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(HASH_REGISTRY_PATH), exist_ok=True)
        with open(HASH_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _checar_duplicado(caminho: str, dom: str, slug: str, res: dict) -> bool:
    """Se outro arquivo com o MESMO conteúdo já existe em outra pasta/domínio,
    apaga este (duplicado) e conta em res['dups']. Retorna True se era dup."""
    try:
        import hashlib
        h = hashlib.sha1()
        with open(caminho, "rb") as f:
            for bloco in iter(lambda: f.read(65536), b""):
                h.update(bloco)
        sha = h.hexdigest()
        reg = _carregar_hashes()
        if sha in reg and os.path.exists(reg[sha]):
            try:
                os.remove(caminho)
            except Exception:
                pass
            res["dups"] = res.get("dups", 0) + 1
            log(f"♻️ '{slug}' conteúdo duplicado de "
                f"{os.path.basename(reg[sha])} — removido", "WARNING")
            return True
        reg[sha] = os.path.abspath(caminho)
        _salvar_hashes(reg)
    except Exception:
        pass
    return False


def _pos_processar(caminho: str, site: str, slug: str, res: dict) -> str:
    """Pós-processamento padrão de um arquivo baixado:
    1) filtro de idioma PT-BR (pode mover p/ descartes);
    2) se permaneceu, registro de hash p/ dedup por conteúdo."""
    idioma = filtrar_idioma(caminho, site, slug)
    if os.path.exists(caminho):
        _checar_duplicado(caminho, site, slug, res)
    return idioma


# ============================================================================
# 2. UTILITÁRIOS
# ============================================================================
def ler_lista_sites(caminho: str = SITES_LISTA) -> List[str]:
    """Lê sites_pdfs.txt ignorando comentários (#) e linhas vazias."""
    sites: List[str] = []
    if not os.path.exists(caminho):
        log(f"⚠️ Lista não encontrada: {caminho}", "WARNING")
        return sites
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            if linha.startswith("http"):
                sites.append(linha.rstrip("/"))
    # remove duplicatas preservando ordem
    vistos = set()
    unicos = []
    for s in sites:
        if s not in vistos:
            vistos.add(s)
            unicos.append(s)
    return unicos


def slug_dominio(url: str) -> str:
    """Nome de pasta seguro a partir do domínio (ex.: baixelivros.com.br).
    Aceita URL completa ou domínio puro (sem http://)."""
    url = (url or "").strip()
    if not url:
        return "site"
    if "://" not in url:
        url = "http://" + url  # urlparse sem esquema trata tudo como caminho
    host = urlparse(url).netloc or "site"
    host = re.sub(r"^www\.", "", host)
    host = re.sub(r"[^a-z0-9.-]", "_", host.lower())
    return host.strip(".")


def slug_livro(url: str) -> str:
    """Último segmento do caminho (ex.: .../dom-casmurro -> dom-casmurro)."""
    caminho = urlparse(url).path.rstrip("/")
    slug = caminho.split("/")[-1] or "livro"
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", slug)
    return slug


def sessao() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def baixar_arquivo(session: requests.Session, url: str, destino: str,
                   esperado: str = "auto", referer: Optional[str] = None,
                   tamanho_min: int = 10_000) -> Tuple[bool, str]:
    """Baixa um arquivo com retry e validação básica.

    esperado: 'pdf' | 'zip' | 'html' | 'txt' | 'auto' (usa Content-Type).
    Retorna (ok, mensagem).
    """
    url = url if url.startswith("http") else "https:" + url
    headers = {}
    if referer:
        headers["Referer"] = referer
    for tentativa in range(1, RETRIES + 2):
        try:
            r = session.get(url, headers=headers, timeout=TIMEOUT, stream=True)
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            # valida por tipo esperado
            ct = (r.headers.get("Content-Type") or "").lower()
            if esperado == "pdf" and "%pdf" not in ct and not url.lower().endswith(".pdf"):
                # tolera servidores que mandam application/octet-stream para .pdf
                if not url.lower().endswith(".pdf"):
                    return False, f"não é PDF (Content-Type: {ct or '?'})"
            tmp = destino + ".part"
            n = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
                    n += len(chunk)
            if n < tamanho_min:
                os.remove(tmp)
                return False, f"arquivo pequeno demais ({n} bytes)"
            os.replace(tmp, destino)
            return True, f"{n} bytes"
        except Exception as e:
            if tentativa > RETRIES:
                return False, f"erro: {e}"
            time.sleep(1.5 * tentativa)
    return False, "falhou após retries"


def validar_pdf(caminho: str) -> bool:
    """Confere se o arquivo começa com %PDF- e tem tamanho mínimo."""
    try:
        if os.path.getsize(caminho) < 10_000:
            return False
        with open(caminho, "rb") as f:
            return f.read(5) == b"%PDF-"
    except Exception:
        return False


def extrair_texto_pdf_amostra(caminho: str, max_paginas: int = 3) -> str:
    """Extrai amostra de texto de um PDF (primeiras páginas) para filtro de idioma."""
    if not FITZ_AVAILABLE:
        return ""
    try:
        doc = fitz.open(caminho)
        partes = []
        for i in range(min(max_paginas, doc.page_count)):
            partes.append(doc[i].get_text())
        doc.close()
        return "\n".join(partes)
    except Exception:
        return ""


def extrair_texto_html(html_bytes: bytes, url: str = "") -> str:
    """Extrai o texto limpo de um HTML (BeautifulSoup)."""
    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
    except Exception:
        return ""


def descompactar_zip(caminho_zip: str, pasta_destino: str) -> bool:
    """Extrai um zip com segurança (evita path traversal)."""
    try:
        os.makedirs(pasta_destino, exist_ok=True)
        with zipfile.ZipFile(caminho_zip) as z:
            for membro in z.namelist():
                destino = os.path.normpath(os.path.join(pasta_destino, membro))
                if not destino.startswith(os.path.normpath(pasta_destino)):
                    continue
                if membro.endswith("/"):
                    os.makedirs(destino, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with z.open(membro) as src, open(destino, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        return True
    except Exception as e:
        log(f"⚠️ Falha ao descompactar {caminho_zip}: {e}", "WARNING")
        return False


def html_para_txt_arquivo(origem_html: str, destino_txt: str) -> Tuple[bool, str]:
    """Lê um arquivo HTML e salva o texto limpo em destino_txt."""
    try:
        with open(origem_html, "rb") as f:
            html = f.read()
        texto = extrair_texto_html(html)
        if len(texto) < 500:
            return False, "pouco texto extraído"
        with open(destino_txt, "w", encoding="utf-8") as f:
            f.write(texto)
        return True, f"{len(texto)} chars"
    except Exception as e:
        return False, f"erro: {e}"


# ============================================================================
# 3.5 TRATAMENTO DE PÁGINAS WEB (blogs/sites abertos) — remoção de BACKLINKS
# ============================================================================
# Ao importar conteúdo de blogs/portais, o texto cru vem cheio de:
#   navegação, menus, rodapé, 'leia também', propagandas, caixas sociais,
#   listas de links (backlinks). Tudo isso polui o treino. Estas funções
#   removem esses blocos ANTES de salvar o texto.

# Classes/ids típicos de blocos que NÃO são conteúdo (propaganda/navegação)
BLOCOS_INDESEJADOS = [
    "ad", "ads", "advert", "banner", "menu", "nav", "navbar", "sidebar",
    "related", "recomend", "recommend", "social", "share", "comment",
    "newsletter", "subscribe", "popup", "modal", "footer", "breadcrumb",
    "pagination", "tags", "categories", "author-box", "widget", "promo",
    "cta", "mais-lidas", "leia-tambem", "leia também", "outros-links",
    "links-uteis", "links úteis", "footer-links", "menu-footer", "topo",
    "cookies", "cookie", "consent", "gpt-ad", "ad-slot", "adsense",
]

# tags que nunca são conteúdo
TAGS_LIXO = ["script", "style", "noscript", "iframe", "form", "svg",
             "canvas", "object", "embed", "audio", "video", "figure"]


def _classe_id_indesejado(tag) -> bool:
    """True se a tag tem class/id típico de bloco não-conteúdo."""
    id_ = (tag.get("id") or "").lower()
    cls = (" ".join(tag.get("class") or [])).lower()
    for k in BLOCOS_INDESEJADOS:
        if k in id_ or k in cls:
            return True
    return False


def _densidade_links(tag) -> float:
    """Frações do texto do bloco que está dentro de <a>. Blocos com muitos
    links (backlinks, 'veja também') têm densidade alta e devem ser removidos."""
    links = tag.find_all("a")
    if not links:
        return 0.0
    total = len(tag.get_text(" ", strip=True))
    if total == 0:
        return 1.0
    texto_links = sum(len(a.get_text(" ", strip=True)) for a in links)
    return texto_links / total


def extrair_texto_artigo(html_bytes: bytes) -> str:
    """Extrai o TEXTO LIMPO de uma página (artigo/blog/portal), removendo
    backlinks, navegação, propaganda e blocos de links. É o 'tratamento ao
    importar' para não carregar lixo junto com o conteúdo."""
    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
    except Exception:
        return ""
    # 1) remove tags que nunca são conteúdo
    for tag in soup(TAGS_LIXO):
        tag.decompose()
    # 2) remove blocos por classe/id (navegação, ads, rodapé...)
    for tag in soup.find_all(True):
        try:
            if _classe_id_indesejado(tag):
                tag.decompose()
        except Exception:
            pass
    # 3) remove nav/aside/footer (semânticos de não-conteúdo)
    for tag in soup(["nav", "aside", "footer", "header"]):
        tag.decompose()
    # 4) remove blocos com alta densidade de links (backlinks / 'veja também')
    for tag in list(soup.find_all(["div", "section", "ul", "ol", "table"])):
        try:
            if _densidade_links(tag) > 0.5:
                tag.decompose()
        except Exception:
            pass
    # 5) prioriza o corpo principal do artigo
    corpo = soup.select_one("article") or soup.select_one("main") \
        or soup.select_one("[itemprop='articleBody']") or soup.body or soup
    texto = corpo.get_text("\n")
    # limpeza final de texto
    texto = re.sub(r"[ \t]+|\u00a0", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r"^[ \t]+|[ \t]+$", "", texto, flags=re.M)
    return texto.strip()


def _links_internos(soup, site: str, max_links: int = 60) -> List[str]:
    """Links do MESMO domínio que parecem páginas de conteúdo (exclui
    categorias, tags, feeds, arquivos e âncoras). Links externos = backlinks
    -> nunca seguidos."""
    dom = urlparse(site).netloc
    EXCLUIR = [
        r"(/tag/|/tags/|/categoria|/category|/autor|/author)",
        r"(/page/|\?page=|\?p=|/pagina)", r"(/feed|/rss|/wp-|/login|/logout)",
        r"(#|javascript:)",
        r"\.(jpg|jpeg|png|gif|webp|pdf|zip|rar|mp4|css|js)(\?|$)",
    ]
    vistos: List[str] = []
    for a in soup.select("a[href]"):
        h = a.get("href") or ""
        h_abs = requests.compat.urljoin(site, h)
        if urlparse(h_abs).netloc != dom:
            continue  # link externo = backlink -> ignora
        if any(re.search(p, h_abs, re.I) for p in EXCLUIR):
            continue
        if h_abs in vistos:
            continue
        caminho = urlparse(h_abs).path.strip("/")
        if not caminho or len(caminho) < 8:
            continue  # home / urls curtas
        vistos.append(h_abs)
        if len(vistos) >= max_links:
            break
    return vistos


# ============================================================================
# 3. FILTRO DE IDIOMA (PT-BR vs PT-PT)
# ============================================================================
# Palavras/expressões típicas de CADA variante. Quanto mais marcações, mais
# confiável o resultado. É uma heurística (não perfeita), mas separa bem.
PALAVRAS_BR = [
    "você", "vocês", "também", "conosco", "a gente", "ônibus", "futebol",
    "menino", "moleque", "açúcar", "geleia", "sorvete", "banheiro", "celular",
    "cafezinho", "legal", "muito bom", "beleza", "puxa", "tá", "né",
    "computador", "geladeira", "torcida", "churrasco", "estádio", "molecada",
    "café da manhã", "bate-papo", "gente boa", "vamos lá", "de jeito nenhum",
    "nossa", "uai", "meu deus", "que legal", "bolacha", "coxinha", "pão de queijo",
]
PALAVRAS_PT = [
    # SÓ palavras que NÃO são usadas no português do Brasil (evita falsos
    # positivos — ex.: 'menina', 'rapaz', 'elevador', 'presunto' são comuns no BR)
    "autocarro", "comboio", "telemóvel", "casa de banho", "pequeno-almoço",
    "frigorífico", "bica", "gajo", "miúdo", "bebé", "candeeiro",
    "esquentador", "ordenado", "fiambre", "talho", "papelaria",
    "vós", "connosco", "facto", "óptimo", "acção",
    "actual", "director", "colecção", "contacto", "projecto", "objecto",
    "adoptar", "excepção", "reflectir", "correcto", "pá", "bué", "fixe",
    "berlinde", "autoclismo", "tarjeta", "pisa-papéis", "trambolho",
    "criado-mudo", "táxi", "tourada", "chávena", "grelhador", "bifana",
    "croquete", "pregão", "fato de banho", "casa de banho", "caixote do lixo",
]
# Conjugações 2ª pessoa (muito comum em PT-PT, raro no BR com 'tu')
PADROES_PT_TU = [
    r"\btu és\b", r"\btu vais\b", r"\btu tens\b", r"\btu fazes\b",
    r"\btu viste\b", r"\btu ficaste\b", r"\btu disseste\b", r"\btu foste\b",
    r"\btu queres\b", r"\btu sabes\b", r"\btu podes\b", r"\btu estás\b",
]


def detectar_pt_br(texto: str) -> Tuple[str, float]:
    """Retorna ('br'|'pt'|'desconhecido', score).

    score > 0 -> tende a BR; score < 0 -> tende a PT.
    Só decide quando há evidência suficiente.
    """
    if not texto:
        return "desconhecido", 0.0
    t = texto.lower()
    n_br = sum(1 for p in PALAVRAS_BR if p in t)
    n_pt = sum(1 for p in PALAVRAS_PT if p in t)
    for pat in PADROES_PT_TU:
        if re.search(pat, t):
            n_pt += 2  # conjugação 'tu' é sinal forte de PT
    score = n_br - n_pt
    if n_br == 0 and n_pt == 0:
        return "desconhecido", 0.0
    if n_br >= 3 and score > 0:
        return "br", score
    if n_pt >= 3 and score < 0:
        return "pt", score
    # evidência mista/fraca: usa proporção
    if n_pt > 0 and n_br == 0:
        return "pt", score
    if n_br > 0 and n_pt == 0:
        return "br", score
    return "desconhecido", score


def filtrar_idioma(caminho: str, site: str, slug: str) -> str:
    """Roda o filtro PT-BR sobre o arquivo e move para descartes se for PT.

    Retorna 'br' | 'pt' | 'desconhecido' | 'sem_texto'.
    """
    ext = os.path.splitext(caminho)[1].lower()
    texto = ""
    if ext == ".txt":
        try:
            with open(caminho, encoding="utf-8", errors="replace") as f:
                texto = f.read(200_000)
        except Exception:
            texto = ""
    elif ext == ".pdf":
        texto = extrair_texto_pdf_amostra(caminho)
    if not texto or len(texto.strip()) < 200:
        return "sem_texto"
    idioma, score = detectar_pt_br(texto)
    if idioma == "pt":
        destino = os.path.join(PASTA_DESCARTES, site, slug + ext)
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.move(caminho, destino)
            log(f"🚫 '{slug}' parece PORTUGUÊS DE PORTUGAL (score {score}) -> descartado", "WARNING")
        except Exception as e:
            log(f"⚠️ Não consegui mover '{slug}' para descartes: {e}", "WARNING")
    elif idioma == "br":
        log(f"✅ '{slug}' confirmado PT-BR (score {score})")
    else:
        log(f"⚠️ '{slug}' idioma desconhecido (mantido)")
    return idioma


# ============================================================================
# 4. EXTRACTORS (um por domínio; mesmo padrão de verificação)
# ============================================================================

def extrair_baixelivros(site: str, cfg: dict) -> dict:
    """BaixeLivros: listagem -> páginas de livro -> botão #botaodownloadoriginal
    -> URL direta do PDF (parâmetro pdf=...). Validado em 09/08/2026."""
    session = cfg["session"]
    saida = cfg["saida"]
    limite = cfg["limite"]
    verificar = cfg["verificar"]
    delay = cfg["delay"]
    resultados = {"ok": 0, "erro": 0, "pulados": 0, "dups": 0, "links": 0}

    try:
        r = session.get(site, timeout=TIMEOUT)
    except Exception as e:
        log(f"❌ [{slug_dominio(site)}] Falha na listagem: {e}", "ERROR")
        resultados["erro"] += 1
        return resultados
    soup = BeautifulSoup(r.text, "html.parser")

    # Links de livros: dentro de <article>, categoria/livro OU acervo/autor/livro.
    # Exclui 1º segmento que não é livro (licenca, biblioteca, etc).
    BLOCK = {"licenca", "biblioteca", "upload", "download-gratuito", "categoria", "tag", "autor"}
    candidatos: List[str] = []
    for a in soup.select("article a[href]"):
        h = a.get("href") or ""
        m = re.match(r"^https://www\.baixelivros\.com\.br/(?:(acervo)/)?([a-z0-9-]+)/([a-z0-9-]+)/?$", h)
        if not m:
            continue
        seg1 = m.group(2)
        if seg1 in BLOCK:
            continue
        # /acervo/<autor> (2 segmentos, sem livro) = página de autor -> pular
        if m.group(1) == "acervo" and m.group(3) == "":
            continue
        candidatos.append(h)
    candidatos = list(dict.fromkeys(candidatos))
    resultados["links"] = len(candidatos)
    log(f"📚 [{slug_dominio(site)}] {len(candidatos)} candidatos de livro na listagem")

    n_ok = 0
    for i, url_livro in enumerate(candidatos):
        if limite and n_ok >= limite:
            break
        slug = slug_livro(url_livro)
        destino = os.path.join(saida, slug_dominio(site), slug + ".pdf")
        if os.path.exists(destino):
            resultados["pulados"] += 1
            _atualizar_progresso(slug_dominio(site), slug, resultados,
                                 cfg.get("site_i", 0), cfg.get("site_total", 1))
            continue
        if verificar:
            log(f"🔎 [verificar] {url_livro}")
            continue
        try:
            rp = session.get(url_livro, timeout=TIMEOUT)
            sp = BeautifulSoup(rp.text, "html.parser")
            btn = sp.select_one("#botaodownloadoriginal")
            if not btn:
                log(f"⚠️ '{slug}' não tem botão de download (não é livro?)")
                resultados["erro"] += 1
                continue
            href = btn.get("href") or ""
            m = re.search(r"[?&]pdf=([^&]+)", href)
            if not m:
                log(f"⚠️ '{slug}' botão sem URL de PDF")
                resultados["erro"] += 1
                continue
            pdf_url = unquote(m.group(1))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            ok, msg = baixar_arquivo(session, pdf_url, destino, esperado="pdf",
                                     referer=url_livro)
            if ok and validar_pdf(destino):
                n_ok += 1
                resultados["ok"] += 1
                log(f"✅ [{i+1}/{len(candidatos)}] '{slug}' baixado ({msg})")
                _pos_processar(destino, slug_dominio(site), slug, resultados)
            else:
                resultados["erro"] += 1
                log(f"❌ '{slug}' falhou: {msg}")
                if os.path.exists(destino):
                    try:
                        os.remove(destino)
                    except Exception:
                        pass
        except Exception as e:
            resultados["erro"] += 1
            log(f"❌ '{slug}' erro: {e}", "ERROR")
        _atualizar_progresso(slug_dominio(site), slug, resultados,
                             cfg.get("site_i", 0), cfg.get("site_total", 1))
        time.sleep(delay)
    return resultados


def extrair_gutenberg(site: str, cfg: dict) -> dict:
    """Project Gutenberg: busca languages=pt -> página do livro -> formato
    preferido (PDF > HTML read online > HTML zip > TXT). EPUB/Kindle ignorados."""
    session = cfg["session"]
    saida = cfg["saida"]
    limite = cfg["limite"]
    verificar = cfg["verificar"]
    delay = cfg["delay"]
    resultados = {"ok": 0, "erro": 0, "pulados": 0, "dups": 0, "links": 0}

    base = "https://www.gutenberg.org"
    n_ok = 0
    for pagina in range(1, 6):  # até 5 páginas de busca (25/página)
        if limite and n_ok >= limite:
            break
        try:
            r = session.get(f"{base}/ebooks/search/?languages=pt&page={pagina}", timeout=TIMEOUT)
        except Exception as e:
            log(f"❌ [gutenberg.org] página {pagina}: {e}", "ERROR")
            break
        soup = BeautifulSoup(r.text, "html.parser")
        livros = [a.get("href") for a in soup.select("li.booklink a[href]")
                  if re.match(r"^/ebooks/\d+$", a.get("href") or "")]
        if not livros:
            break
        resultados["links"] += len(livros)
        for url_livro in livros:
            if limite and n_ok >= limite:
                break
            slug = "ebook" + url_livro.replace("/ebooks/", "")  # ex.: ebook24824
            base_destino = os.path.join(saida, "gutenberg.org", slug)
            # já baixado (qualquer formato)?
            existentes = [f for f in os.listdir(os.path.join(saida, "gutenberg.org")) if f.startswith(slug + ".")]
            if existentes:
                resultados["pulados"] += 1
                _atualizar_progresso("gutenberg.org", slug, resultados,
                                     cfg.get("site_i", 0), cfg.get("site_total", 1))
                continue
            if verificar:
                log(f"🔎 [verificar] {base}{url_livro}")
                continue
            try:
                rp = session.get(base + url_livro, timeout=TIMEOUT)
                sp = BeautifulSoup(rp.text, "html.parser")
                links = {}
                for a in sp.select("a[href]"):
                    h = a.get("href") or ""
                    hl = h.lower()
                    if "/cache/epub/" not in h and "/files/" not in h:
                        continue
                    if hl.endswith(".pdf") or ".pdf" in hl:
                        links.setdefault("pdf", h)
                    elif hl.endswith("-images.html") or hl.endswith("-h.html") or hl.endswith(".html"):
                        links.setdefault("html", h)
                    elif hl.endswith(".zip"):
                        links.setdefault("zip", h)
                    elif hl.endswith(".txt"):
                        links.setdefault("txt", h)
                os.makedirs(base_destino, exist_ok=True)
                baixado = False
                # 1) PDF
                if links.get("pdf"):
                    ok, msg = baixar_arquivo(session, links["pdf"],
                                             os.path.join(base_destino, slug + ".pdf"),
                                             esperado="pdf", referer=base + url_livro)
                    if ok and validar_pdf(os.path.join(base_destino, slug + ".pdf")):
                        resultados["ok"] += 1
                        n_ok += 1
                        baixado = True
                        log(f"✅ '{slug}' PDF baixado ({msg})")
                        _pos_processar(os.path.join(base_destino, slug + ".pdf"),
                                       "gutenberg.org", slug, resultados)
                    else:
                        log(f"⚠️ '{slug}' PDF falhou ({msg}), tentando HTML...")
                # 2) HTML read online
                if not baixado and links.get("html"):
                    ok, msg = baixar_arquivo(session, links["html"],
                                             os.path.join(base_destino, slug + ".html"),
                                             esperado="html", referer=base + url_livro)
                    if ok:
                        ok2, msg2 = html_para_txt_arquivo(
                            os.path.join(base_destino, slug + ".html"),
                            os.path.join(base_destino, slug + ".txt"))
                        if ok2:
                            resultados["ok"] += 1
                            n_ok += 1
                            baixado = True
                            log(f"✅ '{slug}' HTML -> texto ({msg2})")
                            _pos_processar(os.path.join(base_destino, slug + ".txt"),
                                           "gutenberg.org", slug, resultados)
                        else:
                            log(f"⚠️ '{slug}' HTML sem texto: {msg2}")
                    else:
                        log(f"⚠️ '{slug}' HTML falhou ({msg})")
                # 3) HTML zip
                if not baixado and links.get("zip"):
                    zip_path = os.path.join(base_destino, slug + ".zip")
                    ok, msg = baixar_arquivo(session, links["zip"], zip_path,
                                             esperado="zip", referer=base + url_livro)
                    if ok and descompactar_zip(zip_path, os.path.join(base_destino, "html")):
                        htmls = [os.path.join(base_destino, "html", f)
                                 for f in os.listdir(os.path.join(base_destino, "html"))
                                 if f.lower().endswith(".html")]
                        if htmls:
                            texto_total = []
                            for h in sorted(htmls):
                                try:
                                    with open(h, "rb") as f:
                                        texto_total.append(extrair_texto_html(f.read()))
                                except Exception:
                                    pass
                            texto = "\n\n".join(t for t in texto_total if t)
                            if len(texto) >= 500:
                                with open(os.path.join(base_destino, slug + ".txt"),
                                          "w", encoding="utf-8") as f:
                                    f.write(texto)
                                resultados["ok"] += 1
                                n_ok += 1
                                baixado = True
                                log(f"✅ '{slug}' HTML zip -> texto ({len(texto)} chars)")
                                _pos_processar(os.path.join(base_destino, slug + ".txt"),
                                               "gutenberg.org", slug, resultados)
                    if not baixado:
                        log(f"⚠️ '{slug}' HTML zip sem resultado ({msg})")
                # 4) TXT
                if not baixado and links.get("txt"):
                    ok, msg = baixar_arquivo(session, links["txt"],
                                             os.path.join(base_destino, slug + ".txt"),
                                             esperado="txt", referer=base + url_livro)
                    if ok:
                        resultados["ok"] += 1
                        n_ok += 1
                        baixado = True
                        log(f"✅ '{slug}' TXT baixado ({msg})")
                        _pos_processar(os.path.join(base_destino, slug + ".txt"),
                                       "gutenberg.org", slug, resultados)
                if not baixado:
                    resultados["erro"] += 1
                    log(f"⚠️ '{slug}' sem formato aceito (PDF/HTML/HTML zip/TXT)")
            except Exception as e:
                resultados["erro"] += 1
                log(f"❌ '{slug}' erro: {e}", "ERROR")
            _atualizar_progresso("gutenberg.org", slug, resultados,
                                 cfg.get("site_i", 0), cfg.get("site_total", 1))
            time.sleep(delay)
    return resultados


def extrair_generico(site: str, cfg: dict) -> dict:
    """Heurística genérica: procura links .pdf diretos na página.

    Muitos sites têm anti-bot (Cloudflare) ou exigem cliques; nesses casos o
    requests falha e o erro é registrado — preparado para evoluir por domínio.
    """
    session = cfg["session"]
    saida = cfg["saida"]
    limite = cfg["limite"]
    verificar = cfg["verificar"]
    delay = cfg["delay"]
    resultados = {"ok": 0, "erro": 0, "pulados": 0, "dups": 0, "links": 0}
    dom = slug_dominio(site)

    try:
        r = session.get(site, timeout=TIMEOUT)
    except Exception as e:
        log(f"❌ [{dom}] Falha: {e} (provável anti-bot/Cloudflare — avaliar)", "ERROR")
        resultados["erro"] += 1
        return resultados
    if "cloudflare" in r.text[:5000].lower() or r.status_code in (403, 503):
        log(f"⚠️ [{dom}] Bloqueado (Cloudflare/captcha). Precisa de navegador real.", "WARNING")
        resultados["erro"] += 1
        return resultados
    soup = BeautifulSoup(r.text, "html.parser")
    pdfs: List[str] = []
    for a in soup.select("a[href]"):
        h = a.get("href") or ""
        if h.lower().endswith(".pdf"):
            pdfs.append(h if h.startswith("http") else requests.compat.urljoin(site, h))
    pdfs = list(dict.fromkeys(pdfs))
    resultados["links"] = len(pdfs)
    log(f"📄 [{dom}] {len(pdfs)} PDFs diretos encontrados")

    n_ok = 0
    for i, url_pdf in enumerate(pdfs):
        if limite and n_ok >= limite:
            break
        slug = slug_livro(url_pdf) or f"pdf_{i:04d}"
        if not slug.endswith(".pdf"):
            slug += ".pdf"
        destino = os.path.join(saida, dom, slug)
        if os.path.exists(destino):
            resultados["pulados"] += 1
            _atualizar_progresso(dom, slug, resultados,
                                 cfg.get("site_i", 0), cfg.get("site_total", 1))
            continue
        if verificar:
            log(f"🔎 [verificar] {url_pdf}")
            continue
        ok, msg = baixar_arquivo(session, url_pdf, destino, esperado="pdf", referer=site)
        if ok and validar_pdf(destino):
            n_ok += 1
            resultados["ok"] += 1
            log(f"✅ [{i+1}/{len(pdfs)}] '{slug}' ({msg})")
            _pos_processar(destino, dom, slug.replace(".pdf", ""), resultados)
        else:
            resultados["erro"] += 1
            log(f"❌ '{slug}' falhou: {msg}")
        _atualizar_progresso(dom, slug, resultados,
                             cfg.get("site_i", 0), cfg.get("site_total", 1))
        time.sleep(delay)
    return resultados


def extrair_site_aberto(site: str, cfg: dict) -> dict:
    """Blogs / portais / bibliotecas digitais de PUBLICAÇÃO ABERTA.

    Estratégia (mesma verificação em camadas):
      1. PDFs diretos na página inicial  -> baixa como .pdf
      2. Links internos (artigos/páginas) -> extrai TEXTO LIMPO (sem backlinks,
         sem navegação/propaganda) e salva como .txt
    Segue links apenas do MESMO domínio (backlinks externos são ignorados).
    --profundidade: 1 = só a home; 2 = home + páginas linkadas (para compêndios
    como o wikidot). Sempre com dedupe e limite para não explodir.
    """
    session = cfg["session"]
    saida = cfg["saida"]
    limite = cfg["limite"]
    verificar = cfg["verificar"]
    delay = cfg["delay"]
    profundidade = int(cfg.get("profundidade", 1))
    resultados = {"ok": 0, "erro": 0, "pulados": 0, "dups": 0, "links": 0}
    dom = slug_dominio(site)
    n_ok = 0

    # BFS limitado: fila de (url, profundidade)
    fila = [(site, 0)]
    visitados: set = set()
    while fila:
        url, prof = fila.pop(0)
        if url in visitados:
            continue
        visitados.add(url)
        try:
            r = session.get(url, timeout=TIMEOUT)
        except Exception as e:
            resultados["erro"] += 1
            log(f"❌ [{dom}] falha em {url}: {e}", "ERROR")
            continue
        if r.status_code != 200:
            resultados["erro"] += 1
            log(f"⚠️ [{dom}] HTTP {r.status_code} em {url}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")

        # 1) PDFs diretos nesta página
        for a in soup.select("a[href]"):
            h = a.get("href") or ""
            if not h.lower().endswith(".pdf"):
                continue
            pdf_url = h if h.startswith("http") else requests.compat.urljoin(url, h)
            slug = slug_livro(pdf_url) or f"pdf_{len(visitados)}"
            destino = os.path.join(saida, dom, slug)
            if os.path.exists(destino):
                resultados["pulados"] += 1
                _atualizar_progresso(dom, slug, resultados,
                                     cfg.get("site_i", 0), cfg.get("site_total", 1))
                continue
            if verificar:
                log(f"🔎 [verificar] {pdf_url}")
                continue
            ok, msg = baixar_arquivo(session, pdf_url, destino, esperado="pdf", referer=url)
            if ok and validar_pdf(destino):
                n_ok += 1
                resultados["ok"] += 1
                log(f"✅ [{dom}] PDF '{slug}' ({msg})")
                _pos_processar(destino, dom, slug.replace(".pdf", ""), resultados)
            else:
                resultados["erro"] += 1
                log(f"❌ [{dom}] PDF '{slug}' falhou: {msg}")
            _atualizar_progresso(dom, slug, resultados,
                                 cfg.get("site_i", 0), cfg.get("site_total", 1))
            if limite and n_ok >= limite:
                return resultados

        # 2) páginas internas (artigos) — só se ainda há profundidade
        if prof >= profundidade:
            continue
        alvos = _links_internos(soup, url)
        resultados["links"] += len(alvos)
        for alvo in alvos:
            if limite and n_ok >= limite:
                return resultados
            slug = slug_livro(alvo)
            destino = os.path.join(saida, dom, slug + ".txt")
            if os.path.exists(destino):
                resultados["pulados"] += 1
                _atualizar_progresso(dom, slug, resultados,
                                     cfg.get("site_i", 0), cfg.get("site_total", 1))
                continue
            if verificar:
                log(f"🔎 [verificar] {alvo}")
                continue
            try:
                rp = session.get(alvo, timeout=TIMEOUT)
                texto = extrair_texto_artigo(rp.content)
                if len(texto) < 500:
                    log(f"⚠️ [{dom}] '{slug}' pouco texto ({len(texto)} chars)")
                    resultados["erro"] += 1
                    continue
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(destino, "w", encoding="utf-8") as f:
                    f.write(texto)
                n_ok += 1
                resultados["ok"] += 1
                log(f"✅ [{dom}] artigo '{slug}' ({len(texto)} chars, sem backlinks)")
                _pos_processar(destino, dom, slug, resultados)
            except Exception as e:
                resultados["erro"] += 1
                log(f"❌ [{dom}] '{slug}' erro: {e}", "ERROR")
            _atualizar_progresso(dom, slug, resultados,
                                 cfg.get("site_i", 0), cfg.get("site_total", 1))
            time.sleep(delay)
            # enfileira subpáginas (profundidade 2) — sempre do mesmo domínio
            if prof + 1 < profundidade:
                fila.append((alvo, prof + 1))
    return resultados


# Domínio -> extrator. Sem match, usa o genérico.
EXTRACTORS: Dict[str, callable] = {
    "baixelivros.com.br": extrair_baixelivros,
    "www.baixelivros.com.br": extrair_baixelivros,
    "gutenberg.org": extrair_gutenberg,
    "www.gutenberg.org": extrair_gutenberg,
    # sites de publicação aberta (blogs, bibliotecas digitais, compêndios)
    "universia.net": extrair_site_aberto,
    "bibliotecaatilaalmeida.uepb.edu.br": extrair_site_aberto,
    "arquivoestado.sp.gov.br": extrair_site_aberto,
    "bibdig.biblioteca.unesp.br": extrair_site_aberto,
    "bibliotecadigital.unicamp.br": extrair_site_aberto,
    "bib-ci.wikidot.com": extrair_site_aberto,
}


def extrair_site(site: str, cfg: dict) -> dict:
    dom = slug_dominio(site)
    extrator = EXTRACTORS.get(dom, extrair_generico)
    log(f"▶️  [{dom}] usando extrator: {extrator.__name__}")
    return extrator(site, cfg)


# ============================================================================
# 5. MAIN
# ============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrap de livros PDF e sites abertos (PT-BR) a partir de "
                    "sites_pdfs.txt + sites_abertos.txt")
    parser.add_argument("--site", type=str, default=None,
                        help="Filtra por domínio (ex.: baixelivros.com.br)")
    parser.add_argument("--limite", type=int, default=None,
                        help="Máximo de itens baixados por site")
    parser.add_argument("--verificar", action="store_true",
                        help="Só testa a estrutura dos sites (não baixa)")
    parser.add_argument("--saida", type=str, default=PASTA_RAIZ,
                        help="Pasta de saída (padrão: dados/raw/livros)")
    parser.add_argument("--delay", type=float, default=DELAY,
                        help="Pausa entre downloads em segundos")
    parser.add_argument("--profundidade", type=int, default=1, choices=[1, 2],
                        help="Sites abertos: 1=só a home, 2=home+subpáginas "
                             "(compêndios tipo wikidot)")
    parser.add_argument("--sem-filtro-idioma", action="store_true",
                        help="Desativa a verificação de PT-BR")
    args = parser.parse_args()

    sites_pdfs = ler_lista_sites("sites_pdfs.txt")
    sites_abertos = ler_lista_sites("sites_abertos.txt")
    if args.site:
        # --site aceita a URL EXATA (ex.: a escolhida no dropdown do /pdfs)
        # ou só o domínio (ex.: baixelivros.com.br).
        # ⚠️ Ao filtrar por UM site, a OUTRA lista é esvaziada — senão o
        # scraper processa o escolhido E TODOS os sites abertos (bug 13/08).
        site_arg = args.site.strip().rstrip("/")
        if site_arg in sites_pdfs:
            sites_pdfs = [site_arg]
            sites_abertos = []
        elif site_arg in sites_abertos:
            sites_abertos = [site_arg]
            sites_pdfs = []
        else:
            alvo_dom = slug_dominio(site_arg)
            sites_pdfs = [s for s in sites_pdfs
                          if alvo_dom and slug_dominio(s) == alvo_dom]
            sites_abertos = [s for s in sites_abertos
                             if alvo_dom and slug_dominio(s) == alvo_dom]
    if not sites_pdfs and not sites_abertos:
        log("❌ Nenhum site para processar (confira sites_pdfs.txt / "
            "sites_abertos.txt / --site).", "ERROR")
        sys.exit(1)

    log("=" * 70)
    log(f"📚 SCRAP DE LIVROS + SITES ABERTOS — "
        f"{len(sites_pdfs)} site(s) de PDF | {len(sites_abertos)} site(s) aberto(s) | "
        f"modo={'verificação' if args.verificar else 'download'}")
    log("=" * 70)

    session = sessao()
    totais = {"ok": 0, "erro": 0, "pulados": 0, "dups": 0, "links": 0}
    relatorio_sites: List[dict] = []
    PROGRESSO_ATUAL["_inicio"] = time.time()

    def _run(site: str, extrator, indice: int, total: int) -> None:
        nonlocal totais
        PROGRESSO_ATUAL.update({
            "site_i": indice, "site_total": total, "fase": "baixando",
            "msg": f"processando {slug_dominio(site)}",
        })
        cfg = {
            "session": session,
            "saida": args.saida,
            "limite": args.limite,
            "verificar": args.verificar,
            "delay": args.delay,
            "profundidade": args.profundidade,
            "sem_filtro": args.sem_filtro_idioma,
            "site_i": indice,
            "site_total": total,
        }
        res = extrator(site, cfg)
        for k in totais:
            totais[k] += res.get(k, 0)
        relatorio_sites.append({"site": slug_dominio(site),
                                "extrator": extrator.__name__, **res})
        log(f"📊 [{slug_dominio(site)}] ok={res.get('ok',0)} "
            f"erros={res.get('erro',0)} pulados={res.get('pulados',0)} "
            f"dups={res.get('dups',0)} links={res.get('links',0)}")
        time.sleep(args.delay)

    total_sites = len(sites_pdfs) + len(sites_abertos)
    for i, site in enumerate(sites_pdfs, 1):
        _run(site, extrair_site, i, total_sites)          # extrator por domínio ou genérico
    for i, site in enumerate(sites_abertos, len(sites_pdfs) + 1):
        _run(site, extrair_site_aberto, i, total_sites)   # força o de publicação aberta

    log("=" * 70)
    log(f"✅ FIM — baixados: {totais['ok']} | erros: {totais['erro']} | "
        f"pulados (já existiam): {totais['pulados']} | "
        f"dups (conteúdo igual): {totais['dups']} | links vistos: {totais['links']}")
    log(f"📁 Saída: {os.path.abspath(args.saida)}")
    # Relatório por site (o painel /pdfs lê logs/scrap_relatorio.json)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(RELATORIO_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "data": datetime.now().isoformat(),
                "fim": datetime.now().isoformat(),
                "decorrido_s": int(time.time() - PROGRESSO_ATUAL.get("_inicio", time.time())),
                "totais": totais,
                "sites": relatorio_sites,
                "saida": os.path.abspath(args.saida),
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    # Progresso final (100%)
    PROGRESSO_ATUAL.update({
        "pct": 100.0, "fase": "concluido", "msg": "concluido", "atual": "",
        "ok": totais["ok"], "erro": totais["erro"], "pulados": totais["pulados"],
        "dups": totais["dups"],
        "decorrido_s": int(time.time() - PROGRESSO_ATUAL.get("_inicio", time.time())),
        "atualizado": datetime.now().isoformat(),
    })
    _gravar_progresso()
    # Manifesto (para o dashboard ler depois)
    try:
        with open(MANIFESTO_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "data": datetime.now().isoformat(),
                "totais": totais,
                "saida": os.path.abspath(args.saida),
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    main()
