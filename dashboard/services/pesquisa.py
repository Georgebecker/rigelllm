#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pesquisa.py - Serviço de busca na web para o RigelSLM Dashboard
Usa DuckDuckGo como backend padrão.
Com timeout e proteção contra travamentos.
"""
import os
import signal

# Se true, pesquisa é SEMPRE ativada independente do checkbox
PESQUISA_SEMPRE_ATIVA = os.getenv("PESQUISA_SEMPRE_ATIVA", "false").lower() == "true"

# Timeout máximo para a pesquisa (segundos)
PESQUISA_TIMEOUT = int(os.getenv("PESQUISA_TIMEOUT", "8"))


def _resultados_sync(pergunta: str, max_resultados: int) -> list | None:
    """Função síncrona de pesquisa (executada em thread separada).

    Retorna a lista completa de resultados (title, href, body) ou None.
    """
    from ddgs import DDGS
    with DDGS() as ddgs:
        resultados = list(ddgs.text(pergunta, max_results=max_resultados))
        return resultados if resultados else None


def pesquisar(pergunta: str, max_resultados: int = 3):
    """
    Retorna um texto com os resultados da pesquisa no DuckDuckGo.
    Se falhar ou estiver desativado, retorna None.
    Seguro para usar com asyncio.to_thread.
    """
    if not PESQUISA_SEMPRE_ATIVA:
        print("[PESQUISA] Desativada por variável de ambiente.")
        return None
    try:
        print(f"[PESQUISA] Consultando: {pergunta[:50]}... (timeout: {PESQUISA_TIMEOUT}s)")
        resultados = _resultados_sync(pergunta, max_resultados)
        if resultados:
            print(f"[PESQUISA] {len(resultados)} resultados obtidos.")
            return "\n".join([f"- {r.get('body', '')}" for r in resultados])
        else:
            print("[PESQUISA] Nenhum resultado encontrado.")
            return None
    except Exception as e:
        print(f"[PESQUISA] ERRO: {e}")
        return None


def pesquisar_com_fontes(pergunta: str, max_resultados: int = 3):
    """Retorna (texto_contexto, fontes[urls]).

    fontes = [] se a pesquisa falhar/desativar. Usado pelo chat para mostrar
    as fontes usadas na resposta (e salvá-las no feedback/treino).
    """
    if not PESQUISA_SEMPRE_ATIVA:
        return None, []
    try:
        resultados = _resultados_sync(pergunta, max_resultados)
        if resultados:
            texto = "\n".join([f"- {r.get('body', '')}" for r in resultados])
            fontes = [r["href"] for r in resultados if r.get("href")]
            return texto, fontes
        return None, []
    except Exception as e:
        print(f"[PESQUISA] ERRO: {e}")
        return None, []


def verificar_disponivel() -> bool:
    """Verifica se o serviço de busca está disponível (faz uma chamada de teste rápida)."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            list(ddgs.text("teste", max_results=1))
        return True
    except Exception:
        return False
