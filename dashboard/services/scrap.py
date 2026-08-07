#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scrap.py — Scraping de sites → dados limpos em dados/processed/scrap/.

PIPELINE PRONTO (pesquisa 06/08/2026):
  1. Fetch com httpx (headers de navegador, redirects)
  2. trafilatura (padrão-ouro p/ extrair título + conteúdo + data)
     → fallback justext (remove boilerplate) → fallback BeautifulSoup (parágrafos)
  3. Detecta idioma (heurística PT/EN por stopwords) e pontua a QUALIDADE
  4. Salva em dados/raw/scrap/<nome>/ como:
       - jsonl  → formato SFT messages (treinável, compatível com sanitização)
       - txt    → "TÍTULO: ..." + conteúdo (texto puro)
  5. TRATAMENTO AUTOMÁTICO:
       - jsonl → sanitização PT-BR (dashboard.services.sanitizacao)
       - txt   → limpeza de encoding (limpeza.corrigir_codificacao)
  6. Promove para dados/processed/scrap/<nome>/ e limpa origens (HD liberado)

Modo TESTE: testar_url() extrai e avalia a qualidade SEM salvar nada.

Regras de ouro respeitadas: operações leves (1 de cada vez), estado persistido
para sobreviver a --reload, backup implícito (origens só são apagadas após
promover com sucesso).
"""
import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

import httpx

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_SCRAP = PROJETO_ROOT / "dados" / "raw" / "scrap"
SANITIZADOS_SCRAP = PROJETO_ROOT / "dados" / "sanitizados"
PROCESSED_SCRAP = PROJETO_ROOT / "dados" / "processed" / "scrap"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

# Stopwords para heurística de idioma (sem dependências pesadas)
_PT = set("""o a os as de do da dos das um uma uns umas e ou que não é são foi ser em
             para por com sem sob sobre entre depois antes como mais menos muito
             também já ainda assim então porque isso aquilo este esta esses essas
             seu sua seus suas nosso nossa eu tu ele ela nós vós eles elas me te se
             lhe nos vos lo la lhe lhes ao à às aos no na nos nas num numa""".split())
_EN = set("""the a an of to in and or is are was were be been for with without by on
             at from as than then also very much more less this that these those its
             their our your my his her it he she they we you not no yes so because
             if but when while after before between over under about into onto up
             down out off """.split())


# ============================================================================
# Estado global (thread-safe + persistência p/ sobreviver a --reload)
# ============================================================================
_estado: dict = {
    "rodando": False,
    "url": None,
    "etapa": "idle",          # idle | baixando | extraindo | salvando | tratando | promovendo | concluido | erro
    "mensagem": "",
    "percentual": None,
    "inicio": None,
    "fim": None,
    "erro": None,
    "titulo": None,
    "palavras": 0,
    "idioma": None,
    "fonte": None,
    "formato": None,
    "nome": None,
    "saida": None,
    "tratado_exemplos": 0,
    "limpos_origens": 0,
    "paginas": 0,            # nº de páginas/matérias do rastreio
    "profundidade": 0,        # profundidade máxima atingida no crawl
    "limite": 1,              # limite de matérias configurado
    "site": None,             # domínio rastreado
}
_lock = threading.Lock()
_PERSISTENCIA = PROJETO_ROOT / "estado" / "scrap_estado.json"


def _persistir() -> None:
    try:
        _PERSISTENCIA.parent.mkdir(parents=True, exist_ok=True)
        _PERSISTENCIA.write_text(json.dumps(_estado, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception:
        pass


def _atualizar(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)
        _persistir()


def get_estado() -> dict:
    with _lock:
        return dict(_estado)


def limpar() -> dict:
    """Reseta o estado para idle (não apaga arquivos)."""
    with _lock:
        for _k in ("rodando", "url", "etapa", "mensagem", "percentual", "inicio",
                   "fim", "erro", "titulo", "palavras", "idioma", "fonte",
                   "formato", "nome", "saida", "tratado_exemplos", "limpos_origens"):
            if _k in ("rodando", "tratado_exemplos", "limpos_origens"):
                _estado[_k] = 0
            elif _k in ("percentual",):
                _estado[_k] = None
            elif _k == "etapa":
                _estado[_k] = "idle"
            else:
                _estado[_k] = None
        _estado["mensagem"] = ""
        _estado["paginas"] = 0
        _estado["profundidade"] = 0
        _estado["limite"] = 1
        _estado["site"] = None
        _persistir()
    return {"ok": True, "mensagem": "Estado do scrap limpo."}


# ============================================================================
# Extração de título + conteúdo (pipeline pronto)
# ============================================================================
def _limpar_espacos(texto: str) -> str:
    texto = re.sub(r"[ \t\u00a0]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _detectar_idioma(texto: str) -> str:
    """Heurística leve PT/EN baseada em stopwords (sem spaCy/langdetect)."""
    palavras = [p for p in re.findall(r"[a-zA-Zà-üÀ-Ü]+", texto.lower()) if len(p) > 2]
    if not palavras:
        return "?"
    n = len(palavras)
    pt = sum(1 for p in palavras if p in _PT)
    en = sum(1 for p in palavras if p in _EN)
    if pt / n > 0.06 and pt > en:
        return "pt"
    if en / n > 0.06 and en > pt:
        return "en"
    return "?"


def _estatisticas(texto: str) -> dict:
    palavras = len(re.findall(r"\S+", texto))
    sentencas = max(1, len(re.findall(r"[.!?…](?:\s|$)", texto)))
    chars = len(texto)
    media = round(palavras / sentencas, 1) if sentencas else 0
    return {"palavras": palavras, "sentencas": sentencas, "caracteres": chars,
            "media_palavras_sentenca": media}


def _pontuar_qualidade(conteudo: str, titulo: str, idioma: str) -> int:
    """Score 0-100: o quão aproveitável é o texto extraído."""
    score = 0
    palavras = len(conteudo.split())
    if palavras >= 500:
        score += 40
    elif palavras >= 200:
        score += 30
    elif palavras >= 100:
        score += 20
    elif palavras >= 40:
        score += 10
    if titulo:
        score += 15
    if idioma == "pt":
        score += 25
    elif idioma == "en":
        score += 10
    if palavras and palavras / max(1, len(re.findall(r"[.!?…](?:\s|$)", conteudo))) > 200:
        score -= 20
    return max(0, min(100, score))


def extrair_url(url: str, html: str | None = None) -> dict:
    """Busca a página (ou usa html já baixado) e extrai título + conteúdo.

    Retorna dict com ok, titulo, conteudo, idioma, data, fonte, estatísticas.
    Levanta exceção em falha de rede/HTTP.
    """
    if html is None:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url, headers=HEADERS)
            resp.raise_for_status()
            html = resp.text
            url = str(resp.url)  # URL final (após redirects)

    resultado = {"ok": True, "url": url, "titulo": None, "conteudo": None,
                 "idioma": "?", "data": None, "autor": None, "fonte": None}
    # 1) trafilatura — padrão-ouro
    try:
        from trafilatura import extract, extract_metadata
        texto = extract(html, include_comments=False, include_tables=False,
                        favor_precision=True, output_format="txt")
        md = extract_metadata(html, default_url=url)
        if texto and len(texto.split()) >= 20:
            resultado["conteudo"] = texto
            resultado["fonte"] = "trafilatura"
            if md:
                resultado["titulo"] = md.title or None
                resultado["autor"] = md.author or None
                resultado["data"] = md.date or None
    except Exception:
        pass

    soup = None
    # 2) fallback justext (remove boilerplate) + título via <title>
    if not resultado["conteudo"]:
        try:
            from justext import justext
            paragrafos = justext(html, stoplist="Portuguese")
            texto_je = "\n\n".join(p.text for p in paragrafos if not p.is_boilerplate)
            if texto_je and len(texto_je.split()) >= 20:
                resultado["conteudo"] = texto_je
                resultado["fonte"] = "justext"
        except Exception:
            pass

    # 3) fallback final: BeautifulSoup (parágrafos do <body>)
    if not resultado["conteudo"]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header",
                             "aside", "form", "noscript", "iframe"]):
                tag.decompose()
            paragrafos = soup.find_all("p")
            if paragrafos:
                conteudo = "\n\n".join(p.get_text(" ", strip=True) for p in paragrafos)
                if len(conteudo.split()) >= 20:
                    resultado["conteudo"] = conteudo
                    resultado["fonte"] = "bs4"
        except Exception:
            pass

    # Título (se ainda faltar) via <title>/h1
    if not resultado["titulo"]:
        try:
            if soup is None:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
            t = soup.find("title") or soup.find("h1")
            if t:
                resultado["titulo"] = t.get_text(strip=True) or None
        except Exception:
            pass

    if not resultado["conteudo"]:
        return {"ok": False, "url": url, "erro": "Não foi possível extrair conteúdo desta página."}

    resultado["conteudo"] = _limpar_espacos(resultado["conteudo"])
    resultado["idioma"] = _detectar_idioma(resultado["conteudo"])
    resultado.update(_estatisticas(resultado["conteudo"]))
    resultado["score"] = _pontuar_qualidade(resultado["conteudo"], resultado["titulo"],
                                            resultado["idioma"])
    return resultado


def testar_url(url: str) -> dict:
    """Modo teste: extrai e avalia a qualidade SEM salvar nada."""
    try:
        r = extrair_url(url)
    except Exception as e:
        return {"ok": False, "url": url, "erro": f"{type(e).__name__}: {e}"}
    if not r.get("ok"):
        return r
    r["amostra"] = r["conteudo"][:600]
    return r


# ============================================================================
# Crawler por SITE (profundidade, limite, estatísticas) — requisito 06/08
# ============================================================================
def _fetch_html(url: str) -> tuple[str, str]:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        resp = client.get(url, headers=HEADERS)
        resp.raise_for_status()
        return resp.text, str(resp.url)


def _links_internos(html: str, base_url: str) -> list:
    """Links internos do MESMO domínio (ignora âncoras, mídia, arquivos)."""
    from urllib.parse import urlparse, urljoin
    from bs4 import BeautifulSoup
    base = urlparse(base_url)
    links = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                continue
            url = urljoin(base_url, href)
            u = urlparse(url)
            if u.scheme not in ("http", "https") or u.netloc != base.netloc:
                continue
            if u.fragment:
                continue
            if any(u.path.lower().endswith(x) for x in
                   (".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".zip", ".rar",
                    ".css", ".js", ".svg", ".mp4", ".mp3")):
                continue
            links.add(u._replace(fragment="").geturl())
    except Exception:
        pass
    return list(links)


def _categoria(url: str, titulo: str | None) -> str:
    """Deriva o TÓPICO do artigo (1º segmento do path ou 1ª palavra do título)."""
    from urllib.parse import urlparse
    seg = [s for s in urlparse(url).path.split("/") if s and s not in ("wiki", "index.php")]
    if seg:
        return re.sub(r"[_\-\+]", " ", seg[0]).title()[:60]
    if titulo:
        return titulo.split()[0].title()[:60]
    return "Geral"


def rastrear_site(url: str, modo: str = "quantidade", max_materias: int = 20,
                  profundidade: int = 2, preferencia: str = "nenhuma") -> tuple:
    """Crawler BFS por links internos do mesmo domínio.

    modo:
      - 'quantidade'  → coleta até max_materias (profundidade é só um TETO de segurança)
      - 'profundidade'→ explora até o nível N (max_materias vira teto de segurança)
    preferencia (usada quando há mais candidatos que o limite):
      - 'novas'      → as mais RECENTES (data do trafilatura/htmldate)
      - 'complexas'  → as mais LONGAS/complexas (por nº de palavras)
      - 'nenhuma'    → ordem natural do crawl

    Retorna (artigos, stats): stats = {site, paginas, profundidade, limite,
    limite_atingido, visitados, modo, preferencia, coletados}.
    """
    from urllib.parse import urlparse
    site = urlparse(url).netloc
    visitados: set = set()
    candidatos: list = []
    fila: list = [(url, 0)]
    prof_max = 0
    # pool de candidatos: para preferência, coleta um pouco mais e ESCOLHE os melhores
    pool_alvo = max_materias if preferencia == "nenhuma" else min(80, max(10, max_materias * 2))
    teto = max(200, pool_alvo * 4)
    while fila and len(candidatos) < pool_alvo and len(visitados) < teto:
        u, d = fila.pop(0)
        if u in visitados:
            continue
        visitados.add(u)
        if d > profundidade:
            continue
        prof_max = max(prof_max, d)
        try:
            html, url_final = _fetch_html(u)
            r = extrair_url(url_final, html=html)
            if r.get("ok"):
                r["categoria"] = _categoria(url_final, r.get("titulo"))
                candidatos.append(r)
            if d < profundidade:
                for link in _links_internos(html, url_final):
                    if link not in visitados:
                        fila.append((link, d + 1))
        except Exception:
            continue
    if preferencia == "novas":
        candidatos.sort(key=lambda a: (a.get("data") or ""), reverse=True)
    elif preferencia == "complexas":
        candidatos.sort(key=lambda a: a.get("palavras", 0), reverse=True)
    artigos = candidatos[:max_materias]
    stats = {"site": site, "paginas": len(artigos), "profundidade": prof_max,
             "limite": max_materias, "limite_atingido": len(candidatos) > max_materias,
             "visitados": len(visitados), "modo": modo, "preferencia": preferencia,
             "coletados": len(candidatos)}
    return artigos, stats


def _gerar_parquet(destino: Path, artigos: list) -> int:
    """Gera rigel_sft.parquet (messages) + rigel_pretrain.parquet (text).

    Schema IDÊNTICO ao limpeza_leve_rigel_v2 (infra de treino):
      - rigel_sft.parquet: messages = list<struct<role, content>> (ChatML/SFT)
      - rigel_pretrain.parquet: coluna `text` (texto corrido)
    """
    from saida_manager import SYSTEM_PROMPT
    import pyarrow as pa
    import pyarrow.parquet as pq
    destino.mkdir(parents=True, exist_ok=True)
    linhas_sft = []
    linhas_pretrain = []
    for a in artigos:
        t = a.get("titulo") or a.get("url")
        linhas_sft.append({"messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Conte sobre: {t}"},
            {"role": "assistant", "content": a["conteudo"]},
        ]})
        linhas_pretrain.append({"text": f"{t}\n\n{a['conteudo']}"})
    # SFT (mesmo schema do limpeza_leve)
    campo_role = pa.field("role", pa.string())
    campo_content = pa.field("content", pa.string())
    struct_turno = pa.struct([campo_role, campo_content])
    schema = pa.schema([pa.field("messages", pa.list_(struct_turno))])
    arrays = [[{"role": m["role"], "content": m["content"]} for m in e["messages"]]
              for e in linhas_sft]
    tabela = pa.Table.from_arrays(
        [pa.array(arrays, type=pa.list_(struct_turno))], schema=schema)
    pq.write_table(tabela, str(destino / "rigel_sft.parquet"))
    # Pretrain
    pq.write_table(pa.table({"text": [e["text"] for e in linhas_pretrain]}),
                   str(destino / "rigel_pretrain.parquet"))
    return len(artigos)


# ============================================================================
# Pipeline de processamento (extrair → salvar → tratar → promover → limpar)
# ============================================================================
def _sanitizar_e_promover(nome: str) -> tuple[int, int]:
    """Sanitização PT-BR do jsonl + promoção p/ processed/scrap. Retorna (tratado, limpos)."""
    import time as _time
    from dashboard.services import sanitizacao
    import shutil as _sh

    origem = str(RAW_SCRAP / nome)
    saida = str(SANITIZADOS_SCRAP / f"scrap_{nome}")
    ini = sanitizacao.iniciar(origem, saida_dir=saida)
    if not ini.get("ok"):
        _atualizar(mensagem=f"⚠️ Sanitização não iniciou: {ini.get('erro', '?')}")
        return 0, 0
    _espera = 0
    while _espera < 1200:  # máx 20 min (1 artigo é rápido)
        _time.sleep(2)
        _espera += 2
        if not sanitizacao.status().get("rodando"):
            break
    st = sanitizacao.status()
    tratado = int(st.get("total_gravados", 0) or 0)
    if tratado > 0:
        destino = PROCESSED_SCRAP / nome
        destino.mkdir(parents=True, exist_ok=True)
        for f in Path(saida).glob("*.jsonl"):
            try:
                _sh.copy2(str(f), str(destino / f.name))
            except Exception:
                pass
    return tratado, 0


def _limpar_origens(nome: str, pastas: list) -> int:
    import shutil as _sh
    limpas = 0
    for alvo in pastas:
        try:
            if alvo.exists():
                if alvo.is_dir():
                    _sh.rmtree(str(alvo))
                else:
                    alvo.unlink()
                limpas += 1
        except Exception:
            pass
    return limpas


def _nome_seguro(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    slug = re.sub(r"[^a-z0-9]+", "_", (urlparse(url).path or "pagina").lower()).strip("_")
    return f"{host}_{slug or 'pagina'}"[:80]


def _trabalho(url: str, formato: str, nome: str, modo: str = "quantidade",
              preferencia: str = "nenhuma", profundidade: int = 0,
              max_materias: int = 1) -> None:
    try:
        # 1) extrai (1 página) ou RASTEIA o site (modo quantidade OU profundidade)
        artigos: list = []
        stats = {"site": None, "paginas": 1, "profundidade": 0,
                 "limite": max_materias, "limite_atingido": False}
        if (modo == "profundidade" and profundidade >= 1) or \
           (modo == "quantidade" and max_materias > 1):
            _atualizar(etapa="extraindo", percentual=5,
                       mensagem=(f"Rastreando o site ({'quantidade: máx ' + str(max_materias) + ' matérias' if modo == 'quantidade' else 'profundidade ' + str(profundidade)})..."))
            if modo == "quantidade":
                # quantidade é o objetivo; profundidade vira TETO de segurança (3)
                artigos, stats = rastrear_site(url, modo="quantidade",
                                               max_materias=max_materias,
                                               profundidade=3,
                                               preferencia=preferencia)
            else:
                # profundidade é o objetivo; max_materias vira teto de segurança
                artigos, stats = rastrear_site(url, modo="profundidade",
                                               max_materias=max_materias,
                                               profundidade=profundidade,
                                               preferencia=preferencia)
            if not artigos:
                _atualizar(etapa="erro", percentual=None,
                           mensagem="❌ Nenhum artigo extraído do site.",
                           erro="Nenhum artigo extraído do site.", fim=datetime.now().isoformat())
                return
        else:
            _atualizar(etapa="extraindo", percentual=10,
                       mensagem="Buscando a página e extraindo título + conteúdo (trafilatura)...")
            r = extrair_url(url)
            if not r.get("ok"):
                _atualizar(etapa="erro", percentual=None, mensagem="❌ " + (r.get("erro") or "falha"),
                           erro=r.get("erro"), fim=datetime.now().isoformat())
                return
            artigos = [r]
            stats["site"] = r.get("url")

        total_palavras = sum(a.get("palavras", 0) for a in artigos)
        titulo = artigos[0].get("titulo") or artigos[0].get("url")
        _atualizar(etapa="salvando", percentual=40, titulo=titulo,
                   palavras=total_palavras, idioma=artigos[0].get("idioma"),
                   fonte=artigos[0].get("fonte"), paginas=stats.get("paginas"),
                   profundidade=stats.get("profundidade"), limite=stats.get("limite"),
                   site=stats.get("site") or artigos[0].get("url"),
                   mensagem=(f"Salvando {len(artigos)} artigo(s) em "
                             f"dados/raw/scrap/{nome}/ ({formato})..."))

        # 2) salva (jsonl SFT com TÓPICO / txt / parquet direto)
        pasta = RAW_SCRAP / nome
        pasta.mkdir(parents=True, exist_ok=True)
        if formato == "jsonl":
            from saida_manager import SYSTEM_PROMPT
            with (pasta / "artigo.jsonl").open("w", encoding="utf-8") as f:
                for a in artigos:
                    t = a.get("titulo") or a.get("url")
                    exemplo = {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"Conte sobre: {t}"},
                            {"role": "assistant", "content": a["conteudo"]},
                        ],
                        "topico": a.get("categoria") or _categoria(a.get("url") or url, t),
                        "url": a.get("url"), "data": a.get("data"), "fonte": a.get("fonte"),
                    }
                    f.write(json.dumps(exemplo, ensure_ascii=False) + "\n")
        elif formato == "txt":
            for i, a in enumerate(artigos, 1):
                cabecalho = (f"TÍTULO: {a.get('titulo') or a.get('url')}\n"
                             f"URL: {a.get('url')}\nDATA: {a.get('data') or ''}\n")
                (pasta / f"artigo_{i:03d}.txt").write_text(
                    cabecalho + "\n" + a["conteudo"], encoding="utf-8")

        # 3) tratamento automático + promoção
        _atualizar(etapa="tratando", percentual=70,
                   mensagem="Tratando (jsonl→sanitização PT-BR / txt→limpeza / parquet→gerado)...")
        tratado = 0
        if formato == "jsonl":
            tratado, _ = _sanitizar_e_promover(nome)
            if tratado == 0:
                # Fallback honesto: promove o bruto mesmo sem passar no filtro
                destino = PROCESSED_SCRAP / nome
                destino.mkdir(parents=True, exist_ok=True)
                for f in (RAW_SCRAP / nome).glob("*.jsonl"):
                    try:
                        import shutil as _sh
                        _sh.copy2(str(f), str(destino / f.name))
                    except Exception:
                        pass
                tratado = len(artigos)
        elif formato == "txt":
            from limpeza import corrigir_codificacao
            import shutil as _sh2
            # Grava numa pasta temporária e move para a subpasta final <nome>/,
            # para o listar() mostrar (o corrigir_codificacao não preserva subpastas).
            tmp = PROCESSED_SCRAP / f".tmp_{nome}"
            tmp.mkdir(parents=True, exist_ok=True)
            corrigir_codificacao(str(RAW_SCRAP / nome), str(tmp), copiar_utf8=True)
            destino = PROCESSED_SCRAP / nome
            destino.mkdir(parents=True, exist_ok=True)
            for f in tmp.glob("*"):
                try:
                    _sh2.move(str(f), str(destino / f.name))
                except Exception:
                    pass
            try:
                _sh2.rmtree(str(tmp))
            except Exception:
                pass
            tratado = len(artigos)
        else:  # parquet — infra pronta p/ treino (rigel_sft + rigel_pretrain)
            destino = PROCESSED_SCRAP / nome
            destino.mkdir(parents=True, exist_ok=True)
            try:
                tratado = _gerar_parquet(destino, artigos)
            except Exception as e:
                _atualizar(mensagem=f"⚠️ Falha ao gerar parquet ({e}) — salvando txt como fallback")
                for i, a in enumerate(artigos, 1):
                    (destino / f"artigo_{i:03d}.txt").write_text(a["conteudo"], encoding="utf-8")
                tratado = len(artigos)

        # 4) limpa origens (HD liberado)
        _atualizar(etapa="promovendo", percentual=90,
                   mensagem="Limpando origens (raw + sanitizado)...")
        limpas = _limpar_origens(nome, [
            RAW_SCRAP / nome,
            SANITIZADOS_SCRAP / f"scrap_{nome}",
        ])
        _atualizar(tratado_exemplos=tratado, limpos_origens=limpas,
                   saida=str(PROCESSED_SCRAP / nome))

        limite_note = (" (limite atingido)" if stats.get("limite_atingido") else "")
        _atualizar(etapa="concluido", percentual=100,
                   mensagem=(f"✅ {stats.get('paginas', len(artigos))} página(s), "
                             f"{total_palavras} palavras (prof. {stats.get('profundidade', 0)})"
                             f"{limite_note} em dados/processed/scrap/{nome}/"),
                   fim=datetime.now().isoformat())
    except Exception as e:
        import traceback
        traceback.print_exc()
        _atualizar(etapa="erro", mensagem=str(e), erro=str(e), percentual=None,
                   fim=datetime.now().isoformat())
    finally:
        _atualizar(rodando=False)


def processar(url: str, formato: str = "jsonl", nome: str | None = None,
              modo: str = "quantidade", preferencia: str = "nenhuma",
              profundidade: int = 0, max_materias: int = 1) -> dict:
    """Inicia o pipeline completo em segundo plano (thread própria).

    modo: 'quantidade' (até max_materias matérias) | 'profundidade' (explora níveis).
    preferencia: 'novas' | 'complexas' | 'nenhuma' — seleção quando há mais candidatos.
    """
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um processamento em andamento."}
    formato = (formato or "jsonl").lower()
    if formato not in ("jsonl", "txt", "parquet"):
        return {"ok": False, "erro": "formato deve ser 'jsonl', 'txt' ou 'parquet'."}
    if modo not in ("quantidade", "profundidade"):
        modo = "quantidade"
    if preferencia not in ("novas", "complexas", "nenhuma"):
        preferencia = "nenhuma"
    try:
        profundidade = max(0, int(profundidade or 0))
        max_materias = max(1, min(200, int(max_materias or 1)))
    except (TypeError, ValueError):
        profundidade, max_materias = 0, 1
    nome = (_nome_seguro(url) if not nome else re.sub(r"[^a-zA-Z0-9_\-]+", "_", nome).strip("_"))[:80]
    _atualizar(rodando=True, url=url, etapa="extraindo", percentual=5, erro=None,
               titulo=None, palavras=0, idioma=None, fonte=None, formato=formato,
               nome=nome, inicio=datetime.now().isoformat(), fim=None,
               mensagem="Iniciando extração...", tratado_exemplos=0, limpos_origens=0,
               paginas=0, profundidade=0, limite=max_materias, site=None)
    threading.Thread(target=_trabalho,
                     args=(url, formato, nome, modo, preferencia, profundidade, max_materias),
                     daemon=True).start()
    return {"ok": True, "mensagem": f"Processamento iniciado ({formato}, {modo}).", "nome": nome}


def listar() -> dict:
    """Lista os scraps em dados/processed/scrap/ com MARCA de sanitização + tamanhos."""
    itens = []
    if PROCESSED_SCRAP.exists():
        for d in sorted(PROCESSED_SCRAP.iterdir()):
            if d.is_dir():
                arqs = []
                total = 0
                for f in d.iterdir():
                    if f.is_file():
                        arqs.append({"nome": f.name, "tamanho_kb": round(f.stat().st_size / 1024, 1)})
                        total += f.stat().st_size
                subpastas = [{"nome": s.name,
                              "tamanho_mb": round(sum(x.stat().st_size for x in s.rglob("*") if x.is_file()) / 1e6, 2)}
                             for s in d.iterdir() if s.is_dir()]
                nomes = " ".join(a["nome"] for a in arqs).lower()
                if "sanitizado" in nomes:
                    tratamento = "sanitizado"
                elif "rigel_pretrain" in nomes or "rigel_sft" in nomes:
                    tratamento = "parquet"
                elif any(a["nome"].endswith(".txt") for a in arqs):
                    tratamento = "limpeza_encoding"
                else:
                    tratamento = "bruto"
                itens.append({
                    "nome": d.name,
                    "arquivos": [a["nome"] for a in arqs],
                    "detalhes": arqs,
                    "tamanho_mb": round(total / 1e6, 2),
                    "sanitizado": tratamento == "sanitizado",
                    "tratamento": tratamento,
                    "subpastas": subpastas,
                })
    return {"ok": True, "itens": itens, "pasta": str(PROCESSED_SCRAP)}
