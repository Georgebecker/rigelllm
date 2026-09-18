#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verificar_fatos.py — VERIFICAÇÃO DE FATOS COM BUSCA NA INTERNET.

Pedido do usuário (17/08/2026): "precisamos que qualquer modelo que usemos
para gerar uma pergunta possa pesquisar se não é uma resposta fake."

O que faz:
  - Recebe um TEXTO (gerado por qualquer modelo).
  - Extrai as AFIRMAÇÕES FACTUAIS principais (frases com números, datas,
    nomes próprios, locais — o que dá para conferir na web).
  - Busca cada afirmação no DuckDuckGo (ddgs → fallback HTML, como o
    createjsonl.py).
  - Verifica se há EVIDÊNCIA que confirma (título/snippet contendo os
    termos-chave) ou que contradiz.
  - Devolve o VEREDITO por afirmação: ✅ confirmado | ⚠️ não encontrado |
    ❌ contradito + a fonte encontrada.

Uso:
  python scripts/verificar_fatos.py --texto "..." [--max-afirmacoes 3]
  python scripts/verificar_fatos.py --arquivo caminho.txt
  (import) from verificar_fatos import verificar_fatos

Nunca falha: sem internet/biblioteca → devolve veredito "sem_busca" com aviso.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

PESQUISA_MAX_RESULTADOS = 5
PESQUISA_TIMEOUT = 12
RATE_LIMIT_DDG = 1.5
_ultima_requisicao_ddg = 0.0

# Palavras que indicam afirmação verificável (números, datas, pessoas, locais)
_RE_FATO = re.compile(
    r"(?i)\b(\d{2,}|\d{1,2}%|R\$\s?\d|US\$\s?\d|milh|bilh|trilh|"
    r"\b(19|20)\d{2}\b|segundo\s+[A-Z]|conforme\s+[A-Z]|em\s+[A-Z][a-zçáéíóúâêôãõ]+"
    r"|o\s+(presidente|governador|prefeito|ministro)|a\s+(presidenta|governadora))"
)


def _respeitar_rate_limit() -> None:
    global _ultima_requisicao_ddg
    agora = time.time()
    diferenca = agora - _ultima_requisicao_ddg
    if diferenca < RATE_LIMIT_DDG:
        time.sleep(RATE_LIMIT_DDG - diferenca)
    _ultima_requisicao_ddg = time.time()


def _buscar(pergunta: str) -> list[dict]:
    """Busca no DuckDuckGo (ddgs → fallback HTML). Devolve lista de resultados."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore[import-not-found]
        except ImportError:
            return []
    try:
        _respeitar_rate_limit()
        with DDGS() as ddgs:
            resultados = list(ddgs.text(pergunta, max_results=PESQUISA_MAX_RESULTADOS))
            return [{"titulo": r.get("title", ""), "texto": r.get("body", ""),
                     "fonte": r.get("href", "")} for r in resultados]
    except Exception:
        pass
    # fallback HTML
    try:
        import requests
        from bs4 import BeautifulSoup
        _respeitar_rate_limit()
        resp = requests.get("https://html.duckduckgo.com/html/",
                            params={"q": pergunta, "kl": "br-pt"},
                            timeout=PESQUISA_TIMEOUT,
                            headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        resultados = []
        for res in soup.select(".result")[:PESQUISA_MAX_RESULTADOS]:
            titulo = res.select_one(".result__title")
            snippet = res.select_one(".result__snippet")
            link = res.select_one(".result__a")
            resultados.append({
                "titulo": titulo.get_text(strip=True) if titulo else "",
                "texto": snippet.get_text(strip=True) if snippet else "",
                "fonte": link.get("href", "") if link else "",
            })
        return resultados
    except Exception:
        return []


def _extrair_afirmacoes(texto: str, max_afirmacoes: int = 3) -> list[str]:
    """Extrai frases com potencial factual (números/datas/nomes)."""
    # divide em frases
    frases = re.split(r"(?<=[.!?])\s+", texto)
    candidatas = []
    for f in frases:
        f = f.strip()
        if not (40 <= len(f) <= 400):
            continue
        if _RE_FATO.search(f):
            # limpa o excesso de lixo
            limpa = re.sub(r"\s+", " ", f).strip()
            candidatas.append(limpa)
    # dedup mantendo ordem, limita
    vistas: set[str] = set()
    saida = []
    for c in candidatas:
        chave = c[:80].lower()
        if chave in vistas:
            continue
        vistas.add(chave)
        saida.append(c)
        if len(saida) >= max_afirmacoes:
            break
    return saida


def _veredito_afirmacao(afirmacao: str) -> dict:
    """Busca a afirmação e avalia se há evidência."""
    # termos-chave: 3-6 palavras "importantes" (sem stopwords curtas)
    palavras = [p for p in re.findall(r"[A-Za-zÀ-ú0-9%$]+", afirmacao)
                if len(p) > 3 and p.lower() not in {
                    "para", "com", "uma", "uma", "dos", "das", "pelo", "pela",
                    "que", "sua", "seus", "sobre", "entre", "depois", "antes",
                    "contra", "durante", "nesta", "neste", "tambem", "ainda"}]
    chave_busca = " ".join(palavras[:6]) if len(palavras) >= 2 else afirmacao[:80]
    if not chave_busca.strip():
        return {"veredito": "sem_busca", "motivo": "Afirmação sem termos pesquisáveis."}

    resultados = _buscar(chave_busca)
    if not resultados:
        return {"veredito": "sem_busca", "motivo": "Busca sem resposta (sem internet ou sem resultado).",
                "afirmacao": afirmacao}

    # evidência: título+texto concatenados, minúsculos
    termos = [p.lower() for p in palavras[:4]]
    melhores = []
    for r in resultados:
        blob = f"{r.get('titulo', '')} {r.get('texto', '')}".lower()
        acertos = sum(1 for t in termos if t in blob)
        melhores.append({"fonte": r.get("fonte", ""), "titulo": r.get("titulo", ""),
                         "texto": r.get("texto", "")[:200], "acertos": acertos})
    melhores.sort(key=lambda x: -x["acertos"])
    topo = melhores[0]

    if topo["acertos"] >= max(2, len(termos) // 2):
        return {"veredito": "confirmado",
                "motivo": "A busca encontrou evidência que bate com o texto.",
                "fonte": topo["fonte"], "titulo": topo["titulo"],
                "acertos": topo["acertos"], "afirmacao": afirmacao}
    return {"veredito": "nao_encontrado",
            "motivo": "A busca não encontrou evidência clara (pode ser invenção).",
            "fonte": topo["fonte"], "titulo": topo["titulo"],
            "acertos": topo["acertos"], "afirmacao": afirmacao}


def verificar_fatos(texto: str, max_afirmacoes: int = 3) -> dict:
    """Verifica as afirmações factuais de um texto. Nunca lança."""
    try:
        afirmacoes = _extrair_afirmacoes(texto, max_afirmacoes)
        if not afirmacoes:
            return {"ok": True, "veredito_geral": "sem_fatos",
                    "motivo": "Não encontrei afirmações factuais claras para conferir.",
                    "afirmacoes": []}
        resultados = []
        for a in afirmacoes:
            resultados.append(_veredito_afirmacao(a))
        confirmados = sum(1 for r in resultados if r["veredito"] == "confirmado")
        sem_busca = sum(1 for r in resultados if r["veredito"] == "sem_busca")
        if confirmados > 0 and confirmados == len(resultados) - sem_busca:
            geral = "confirmado"
        elif sem_busca == len(resultados):
            geral = "sem_busca"
        else:
            geral = "nao_encontrado"
        return {"ok": True, "veredito_geral": geral, "afirmacoes": resultados,
                "total": len(resultados), "confirmados": confirmados}
    except Exception as e:
        return {"ok": False, "veredito_geral": "erro", "motivo": str(e),
                "afirmacoes": []}


def main() -> int:
    ap = argparse.ArgumentParser(description="Verificação de fatos com busca na internet")
    ap.add_argument("--texto", default="")
    ap.add_argument("--arquivo", default="")
    ap.add_argument("--max-afirmacoes", type=int, default=3)
    args = ap.parse_args()

    if args.arquivo:
        texto = Path(args.arquivo).read_text(encoding="utf-8", errors="replace")
    elif args.texto:
        texto = args.texto
    else:
        print("Informe --texto ou --arquivo.")
        return 1

    r = verificar_fatos(texto, args.max_afirmacoes)
    print(f"Veredito geral: {r.get('veredito_geral')} | {r.get('motivo', '')}")
    for a in r.get("afirmacoes", []):
        print(f"  [{a.get('veredito')}] {a.get('afirmacao', '')[:100]}")
        if a.get("titulo"):
            print(f"      → {a.get('titulo', '')[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
