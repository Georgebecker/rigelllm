#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
createjsonl.py - Gerador de dataset JSONL para Fine-Tuning SFT do RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089

Gera conversas sintéticas no formato:
{"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

Arquitetura: Pesquisa web (DuckDuckGo) + Dicionário de Conhecimento (knowledge_base.json)
+ Pontuação de qualidade (2 respostas do Ollama, escolhe a melhor).

MODOS DE USO:
  Geração (Ollama):        python createjsonl.py --count 500 [--usar-topicos-txt]
  Baixar URL e explodir:   python createjsonl.py --download "https://.../dataset.zip"
  HuggingFace:             python createjsonl.py --hf-dataset "org/nome"
  Processar pasta/arquivo: python createjsonl.py --process "caminho/para/dataset"
  Apenas extrair:          python createjsonl.py --extract "arquivo.zip"

SAÍDAS:
  Geração:     dados/gerados/jsonl/dataset_rigel.jsonl (e shards _0002, _0003...)
  Explosão:    dados/gerados/jsonl/<nome>/pasta_001/, pasta_002/ ...
               (no máximo MAX_FILES_POR_PASTA = 5000 arquivos por pasta)
  Downloads:   dados/raw/ (fora do processed)
  Dicionário:  knowledge_base.json

Reutiliza as listas de tópicos de `categories.py` (NÃO modifica nenhum arquivo existente).
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime

# Garante que o diretório do script esteja no path (import de categories.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Garante saída UTF-8 no console (evita UnicodeEncodeError no Windows/cp1252)
for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

import gzip
import glob
import shutil
import tarfile
import threading
import zipfile
from urllib.parse import unquote, urlparse

import requests
from tqdm import tqdm

# ============================================================================
# IMPORT DO ECOSSISTEMA EXISTENTE (categories.py) - REUTILIZAÇÃO OBRIGATÓRIA
# ============================================================================
try:
    from categories import (
        CATEGORIAS_LISTAS,
        PREFIXOS_POR_CATEGORIA,
        TEMPLATES_EXTRAS,
        GRUPOS_CATEGORIAS,
        SAUDACOES,
    )
    _CATEGORIAS_OK = True
except Exception as _e:  # pragma: no cover
    print(f"⚠️ Não foi possível importar categories.py: {_e}")
    print("   Verifique se o script está na raiz do projeto RigelSLM.")
    sys.exit(1)

# ============================================================================
# CONSTANTES
# ============================================================================
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))       # timeout INICIAL
OLLAMA_TIMEOUT_MAX = int(os.getenv("OLLAMA_TIMEOUT_MAX", "600"))  # teto do timeout adaptativo
OLLAMA_TIMEOUT_ESCALA = float(os.getenv("OLLAMA_TIMEOUT_ESCALA", "2.0"))  # multiplicador por tentativa
OLLAMA_TIMEOUT_CPU_FATOR = float(os.getenv("OLLAMA_TIMEOUT_CPU_FATOR", "1.5"))  # CPU é mais lenta
OLLAMA_RETRIES = int(os.getenv("OLLAMA_RETRIES", "3"))
OLLAMA_BACKOFF_BASE = float(os.getenv("OLLAMA_BACKOFF_BASE", "2.0"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "800"))

# Modelos padrão por dispositivo (leves e eficientes)
# ⚠️ NUNCA use 'rigelslm': é o modelo em TREINAMENTO (ainda muito novo).
MODELO_CPU_PADRAO = os.getenv("MODELO_CPU_PADRAO", "gemma2:2b")       # leve, ótimo em PT-BR na CPU
MODELO_GPU_PADRAO = os.getenv("MODELO_GPU_PADRAO", "qwen2.5:7b")      # recomendado p/ Colab/GPU

KNOWLEDGE_BASE_FILE = os.getenv("KNOWLEDGE_BASE_FILE", "knowledge_base.json")
LOG_FILE = os.getenv("CREATEJSONL_LOG", "createjsonl.log")

PESQUISA_TIMEOUT = int(os.getenv("PESQUISA_TIMEOUT", "10"))
PESQUISA_MAX_RESULTADOS = int(os.getenv("PESQUISA_MAX_RESULTADOS", "6"))
CONTEXTO_MIN_PALAVRAS = 300
CONTEXTO_MAX_PALAVRAS = 500

BASE_SCORE = 5.0  # Nota base (0-10) antes dos critérios
SCORE_SEM_REGRA = 3.0  # Teto de nota SEM a Regra de Ouro (impede aprovação no limiar padrão)

# System Prompt FIXO do Rigel — fonte única em saida_manager.py
from saida_manager import SYSTEM_PROMPT

# Frases que indicam "fuga de IA" (penalidade)
FRASES_FUGA_IA = [
    "sou um modelo de linguagem",
    "sou uma ia",
    "sou um programa",
    "não tenho sentimentos",
    "como assistente",
    "como uma ia",
    "enquanto ia",
    "não sou humano",
    "não posso sentir",
]

# Frases genéricas/vagas (penalidade)
FRASES_GENERICAS = [
    "depende",
    "cada caso é um caso",
    "é muito relevante",
    "varia de pessoa para pessoa",
    "depende do contexto",
    "depende de cada",
    "tudo depende",
    "na minha opinião tudo é relativo",
]

# Templates de pergunta de fallback (caso a categoria não tenha prefixos)
TEMPLATES_FALLBACK = [
    "Explique o que é {assunto}",
    "Como funciona {assunto}?",
    "Qual a importância de {assunto}?",
    "O que você sabe sobre {assunto}?",
    "Fale um pouco sobre {assunto}",
]

# Chance de gerar uma SAUDAÇÃO natural (conversa curta) em vez de pergunta informativa
SAUDACAO_CHANCE = float(os.getenv("SAUDACAO_CHANCE", "0.10"))

# Tópicos externos (topicos.txt) como fonte ADICIONAL de assuntos
# (alimentado pelo rss_processor.py e pelo dashboard; hoje usado pelo generation.py)
TOPICOS_TXT_FILE = os.getenv("TOPICOS_TXT_FILE", "topicos.txt")
TOPICOS_TXT_CHANCE = float(os.getenv("TOPICOS_TXT_CHANCE", "0.25"))   # ~25% dos exemplos
TOPICOS_TXT_MAX_LEN = int(os.getenv("TOPICOS_TXT_MAX_LEN", "90"))     # ignora manchetes longas
CATEGORIA_EXTERNA = "topicos_externos"  # categoria virtual p/ contadores/resumo

# Templates para tópicos externos: eles já são FRASES completas (ex: "A abolição
# da escravatura em 1888"), então não combinam com prefixos de substantivo.
TEMPLATES_TOPICOS_EXTERNOS = [
    "Fale sobre {assunto}",
    "Explique {assunto}",
    "O que você sabe sobre {assunto}?",
    "Conte-me sobre {assunto}",
    "Qual a importância de {assunto}?",
    "Como funciona {assunto}?",
    "Qual a origem de {assunto}?",
]

# Verbos típicos de MANCHETE de notícia (declaração) — usados na filtragem.
# Ex: "Diretor da OMS diz que...", "Governo anuncia...", "Time vence..."
VERBOS_MANCHETE = (
    "diz", "dizem", "afirma", "afirmam", "anuncia", "anunciam", "revela",
    "revelam", "confirma", "confirmam", "critica", "criticam", "defende",
    "defendem", "aponta", "apontam", "mostra", "mostram", "ganha",
    "conquista", "conquistou", "nega", "negam", "pede", "pedem",
    "explica", "explicam", "adverte", "alerta", "alertam", "comemora",
    "lamenta", "supera", "atinge", "atingiu", "morre", "morreu",
    "vence", "venceu", "manda", "ordena", "recorre", "recorreu",
    "classifica", "classificou", "oficializa", "oficializou", "rejeita",
    "rejeitou", "aprova", "aprovou", "lança", "lançou", "cria", "criou",
    "investe", "investiu", "compra", "comprou", "vende", "vendeu",
    "abre", "abriu", "fecha", "fechou", "inicia", "iniciou", "conclui",
    "concluiu", "publica", "publicou", "divulga", "divulgou", "registra",
    "registrou", "proíbe", "proibiu", "autoriza", "autorizou", "libera",
    "liberou", "prorroga", "prorrogou", "elege", "elegeu", "derrota",
    "derrotou", "domina", "dominou", "avança", "avançou", "cresce",
    "cresceu", "cai", "caiu", "sobe", "subiu", "centraliza", "centralizou",
    "faz", "fez", "recomenda", "recomendou", "causa", "causou", "aborda",
    "abordam", "discute", "discutem", "analisa", "analisam", "avalia",
    "avaliam", "prevê", "antecipa", "antecipou", "prepara", "preparou",
    "investiga", "investigou", "apresenta", "apresentam", "sugere",
)

# ============================================================================
# PASTAS E LIMITES DE ARQUIVOS
# ============================================================================
PASTA_BASE = "dados"
PASTA_RAW = os.path.join(PASTA_BASE, "raw")          # downloads/arquivos brutos (fora do processed)
PASTA_GERADOS = os.path.join(PASTA_BASE, "gerados")  # dados gerados/explodidos
PASTA_JSONL = os.path.join(PASTA_GERADOS, "jsonl")   # datasets JSONL finais
PASTA_PROCESSED = os.path.join(PASTA_BASE, "processed")  # dados prontos p/ treino (não tocamos)

# Limites (nada superior a 5000 arquivos por pasta)
MAX_FILES_POR_PASTA = int(os.getenv("MAX_FILES_POR_PASTA", "5000"))
EXEMPLOS_POR_ARQUIVO = int(os.getenv("EXEMPLOS_POR_ARQUIVO", "1000"))
MAX_EXEMPLOS_TOTAIS = int(os.getenv("MAX_EXEMPLOS_TOTAIS", "1000000"))

# Contexto completo das páginas (trafilatura, opcional)
CONTEXTO_MAX_PAGINAS = int(os.getenv("CONTEXTO_MAX_PAGINAS", "3"))
CONTEXTO_MAX_POR_PAGINA = int(os.getenv("CONTEXTO_MAX_POR_PAGINA", "2000"))

# Rate limit do DuckDuckGo (evita bloqueio de IP)
RATE_LIMIT_DDG = float(os.getenv("RATE_LIMIT_DDG", "2.0"))

# Checkpoint para retomada (--resume)
CHECKPOINT_FILE = os.getenv("CHECKPOINT_FILE", "checkpoint.json")

# Tópicos bloqueados (sanitização de conteúdo)
TOPICOS_BLOQUEADOS = [
    "como fabricar bomba",
    "como fazer bomba",
    "receita de droga",
    "como produzir droga",
    "como fabricar droga",
    "metanfetamina",
    "como cometer suicídio",
    "como matar alguém",
    "como sequestrar",
    "explosivos caseiros",
    "como hackear",
    "pedofilia",
    "violência doméstica",
]

# Prompt do modelo juiz (--judge-model)
JUDGE_PROMPT = (
    "Você é um avaliador de qualidade de respostas de assistente virtual. "
    "Responda APENAS com um JSON válido no formato: "
    "{\"nota\": 0-10, \"aprovada\": true/false, \"motivo\": \"curto\"}. "
    "Critérios: a resposta deve terminar com UMA pergunta de aprofundamento oferecendo 2 opções "
    "(regra de ouro), ser em português natural, sem frases de IA, sem respostas genéricas e sem truncamento."
)


# ============================================================================
# 1. LOG
# ============================================================================
def log(msg: str) -> None:
    """Registra mensagem no arquivo de log e no terminal."""
    linha = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass
    print(linha)


# ============================================================================
# 2. GERADOR DE PERGUNTAS (usa as listas de categories.py)
# ============================================================================
def _topico_seguro(assunto: str) -> bool:
    """Filtra assuntos com conteúdo bloqueado/inadequado (sanitização)."""
    assunto_low = assunto.lower()
    return not any(bloqueado in assunto_low for bloqueado in TOPICOS_BLOQUEADOS)


def escolher_categoria(contadores: dict | None = None) -> str:
    """
    Escolhe uma categoria. Se `contadores` for informado, usa amostragem
    PONDERADA inversa à representação (categorias menos geradas têm mais
    chance), garantindo um dataset balanceado.
    """
    chaves = [k for k, v in CATEGORIAS_LISTAS.items() if v]
    if not chaves:
        return "conceito"
    # 30% das vezes usa um grupo temático (historia, ciencia, cultura...)
    if GRUPOS_CATEGORIAS and random.random() < 0.3:
        grupo = random.choice(list(GRUPOS_CATEGORIAS.keys()))
        membros = [c for c in GRUPOS_CATEGORIAS.get(grupo, []) if CATEGORIAS_LISTAS.get(c)]
        if membros:
            return random.choice(membros)
    if contadores:
        pesos = [1.0 / (1.0 + contadores.get(c, 0)) for c in chaves]
        return random.choices(chaves, weights=pesos, k=1)[0]
    return random.choice(chaves)


def escolher_assunto(categoria: str) -> str:
    """Escolhe um assunto seguro da lista da categoria."""
    lista = CATEGORIAS_LISTAS.get(categoria) or []
    itens = [i for i in lista if isinstance(i, str) and i.strip() and _topico_seguro(i)]
    if not itens:
        itens = [i for i in lista if isinstance(i, str) and i.strip()]
    if not itens:
        return "o mundo"
    return random.choice(itens)


def _filtrar_topico_externo(linha: str) -> str | None:
    """
    Filtra uma linha do topicos.txt para virar um bom 'assunto'.
    Descarta manchetes de notícia (aspas iniciais, 'título: subtítulo',
    começo numérico, muito longas) e linhas que já são perguntas completas.
    """
    t = linha.strip()
    if not t:
        return None
    if len(t) > TOPICOS_TXT_MAX_LEN:
        return None
    # Manchete com aspas de abertura:  'Diplomacia zen': o que Lula...
    if t.startswith(("'", '"', "“", "‘", "«")):
        return None
    # Aspas em QUALQUER lugar (manchete com citação no meio)
    if "'" in t or '"' in t or "“" in t or "”" in t:
        return None
    # Separador de manchete 'título - fonte' ("O que precisamos - Crianças Sabidas...")
    if " - " in t:
        return None
    # Já começa com frase de pergunta ("o que é...", "quem...", "como...")
    if t.lower().startswith(("o que ", "quem ", "como ", "por que ", "onde ", "quando ")):
        return None
    # Manchete no formato 'título: subtítulo' ou com ';'
    if ":" in t or ";" in t:
        return None
    # Manchete que começa com número ("54 Ceasa's comercializaram...")
    if t[0].isdigit():
        return None
    # Já é pergunta completa? Não serve como 'assunto' para os templates
    if t.endswith("?"):
        return None
    # Mínimo de palavras (evita lixo tipo "A", "O", "E")
    if len(t.split()) < 2:
        return None
    # Manchete com atribuição de pesquisa: "..., segundo nova pesquisa"
    if ", segundo" in t.lower():
        return None
    # Manchete de declaração: começa com palavra capitalizada e tem verbo de
    # notícia logo no início ("Diretor da OMS diz que...", "Governo anuncia...")
    palavras = t.split()
    if len(palavras) >= 3 and palavras[0][0].isupper():
        for w in palavras[1:min(7, len(palavras))]:
            if w.lower().strip(".,:;()") in VERBOS_MANCHETE:
                return None
    return t


def carregar_topicos_externos_filtrados() -> list[str]:
    """
    Carrega e filtra os tópicos do topicos.txt (fonte RSS/dashboard).
    Deduplica e aplica a sanitização de conteúdo (TOPICOS_BLOQUEADOS).
    Retorna [] se o arquivo não existir ou não tiver tópicos aproveitáveis.
    """
    if not os.path.exists(TOPICOS_TXT_FILE):
        return []
    try:
        with open(TOPICOS_TXT_FILE, "r", encoding="utf-8") as f:
            linhas = [l.strip() for l in f]
    except Exception as e:
        print(f"⚠️ Não foi possível ler {TOPICOS_TXT_FILE}: {e}")
        return []
    vistos: set[str] = set()
    resultado: list[str] = []
    for linha in linhas:
        topico = _filtrar_topico_externo(linha)
        if not topico or not _topico_seguro(topico):
            continue
        chave = topico.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(topico)
    return resultado


def _assunto_para_pergunta(assunto: str) -> str:
    """
    Minuscula o artigo inicial para o tópico fluir na pergunta:
    'A abolição da escravatura em 1888' -> 'a abolição da escravatura em 1888'.
    (A versão ORIGINAL é mantida como chave do knowledge_base/contadores.)
    """
    m = re.match(r"^(A|O|As|Os|Uma|Um)\s+(.+)$", assunto, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower() + " " + m.group(2)
    return assunto


def gerar_pergunta(contadores: dict | None = None,
                   topicos_externos: list[str] | None = None) -> tuple[str, str, str]:
    """
    Monta uma pergunta variada e BALANCEADA usando categories.py.
    ~SAUDACAO_CHANCE% das vezes gera uma SAUDAÇÃO/conversa curta natural
    (categoria 'saudacao'), o resto pergunta informativa.
    Se `topicos_externos` for informado (--usar-topicos-txt), ~TOPICOS_TXT_CHANCE%
    das vezes usa um assunto do topicos.txt (fonte RSS/dashboard) em vez das
    listas de categories.py.
    Retorna (pergunta, categoria, assunto).
    """
    # Saudações naturais brasileiras (de categories.py)
    if SAUDACOES and random.random() < SAUDACAO_CHANCE:
        pergunta_saudacao, _resposta_exemplo = random.choice(SAUDACOES)
        return pergunta_saudacao, "saudacao", pergunta_saudacao

    # Tópicos externos (topicos.txt): assunto já é frase completa + templates próprios
    if topicos_externos and random.random() < TOPICOS_TXT_CHANCE:
        assunto = random.choice(topicos_externos)
        categoria = CATEGORIA_EXTERNA
        # Minuscula o artigo inicial p/ fluir na pergunta (original vira chave do contexto)
        assunto_pergunta = _assunto_para_pergunta(assunto)
        opcoes = [t.replace("{assunto}", assunto_pergunta) for t in TEMPLATES_TOPICOS_EXTERNOS]
        pergunta = random.choice(opcoes).strip()
        if not pergunta.endswith("?"):
            pergunta += "?"
        return pergunta, categoria, assunto

    categoria = escolher_categoria(contadores)
    assunto = escolher_assunto(categoria)

    prefixos = PREFIXOS_POR_CATEGORIA.get(categoria) or []
    templates = TEMPLATES_EXTRAS.get(categoria) or []

    opcoes = []
    for p in prefixos:
        opcoes.append(f"{p} {assunto}")
    for t in templates:
        opcoes.append(t.replace("{assunto}", assunto))
    for t in TEMPLATES_FALLBACK:
        opcoes.append(t.replace("{assunto}", assunto))

    pergunta = random.choice(opcoes).strip()
    # Garante pontuação final de pergunta (evita '?' duplicado)
    if not pergunta.endswith("?"):
        pergunta += "?"
    return pergunta, categoria, assunto


# ============================================================================
# 3. MÓDULO DE PESQUISA (DuckDuckGo) + FALLBACK HTML + TEXTO COMPLETO
# ============================================================================
_ultima_requisicao_ddg = 0.0


def _respeitar_rate_limit() -> None:
    """Garante um intervalo mínimo entre requisições ao DuckDuckGo (evita bloqueio)."""
    global _ultima_requisicao_ddg
    agora = time.time()
    diferenca = agora - _ultima_requisicao_ddg
    if diferenca < RATE_LIMIT_DDG:
        time.sleep(RATE_LIMIT_DDG - diferenca)
    _ultima_requisicao_ddg = time.time()


def _baixar_e_extrair_pagina(url: str) -> str | None:
    """Baixa uma URL e extrai o texto principal com trafilatura (biblioteca opcional)."""
    try:
        import trafilatura  # type: ignore[import-not-found]
        baixado = trafilatura.fetch_url(url)
        if not baixado:
            return None
        texto = trafilatura.extract(baixado, include_comments=False,
                                    include_tables=True, no_fallback=False)
        return texto
    except Exception as e:
        print(f"[EXTRAÇÃO] Falha em {url}: {e}")
        return None


def _pesquisar_ddgs(pergunta: str) -> list[dict] | None:
    """Pesquisa usando a biblioteca duckduckgo_search/ddgs (como o projeto)."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore[import-not-found]
        except ImportError:
            print("[PESQUISA] Biblioteca 'ddgs'/'duckduckgo_search' não instalada. "
                  "Instale com: pip install ddgs")
            return None
    try:
        _respeitar_rate_limit()
        with DDGS() as ddgs:
            resultados = list(ddgs.text(pergunta, max_results=PESQUISA_MAX_RESULTADOS))
            return [{"titulo": r.get("title", ""), "texto": r.get("body", ""), "fonte": r.get("href", "")} for r in resultados]
    except Exception as e:
        print(f"[PESQUISA] ddgs falhou ({e}), tentando HTML...")
        return None


def _pesquisar_html(pergunta: str) -> list[dict] | None:
    """Fallback: scrapeia o HTML do DuckDuckGo com requests + BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    try:
        url = "https://html.duckduckgo.com/html/"
        params = {"q": pergunta, "kl": "br-pt"}
        _respeitar_rate_limit()
        resp = requests.get(url, params=params, timeout=PESQUISA_TIMEOUT,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code != 200:
            return None
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
        return resultados or None
    except Exception as e:
        print(f"[PESQUISA] HTML falhou: {e}")
        return None


def _resumir_contexto(resultados: list[dict]) -> str:
    """
    Constrói o contexto para o modelo.
    1) Tenta extrair o TEXTO COMPLETO das páginas reais (trafilatura, opcional).
    2) Se indisponível, cai para os snippets curtos do DuckDuckGo.
    """
    # 1) Texto completo das páginas encontradas
    textos_completos = []
    for r in resultados[:CONTEXTO_MAX_PAGINAS]:
        url = r.get("fonte", "")
        if not url or not url.startswith("http"):
            continue
        texto = _baixar_e_extrair_pagina(url)
        if texto and len(texto) > 200:
            textos_completos.append(texto[:CONTEXTO_MAX_POR_PAGINA])

    if textos_completos:
        texto_bruto = " ".join(textos_completos)
    else:
        # 2) Fallback: snippets curtos do DuckDuckGo
        partes = []
        for r in resultados:
            if r.get("titulo"):
                partes.append(r["titulo"])
            if r.get("texto"):
                partes.append(r["texto"])
        texto_bruto = " ".join(partes)

    palavras = re.findall(r"\S+", texto_bruto)
    if not palavras:
        return ""
    if len(palavras) > CONTEXTO_MAX_PALAVRAS:
        palavras = palavras[:CONTEXTO_MAX_PALAVRAS]
    return " ".join(palavras)


def pesquisar_web(pergunta: str) -> dict | None:
    """
    Busca resumos em português sobre o tópico.
    Retorna {"contexto": ..., "fonte": ...} ou None em caso de falha.
    """
    try:
        resultados = _pesquisar_ddgs(pergunta) or _pesquisar_html(pergunta)
        if not resultados:
            print("[PESQUISA] Nenhum resultado encontrado.")
            return None
        contexto = _resumir_contexto(resultados)
        if not contexto:
            return None
        fonte = next((r.get("fonte") for r in resultados if r.get("fonte")), "")
        return {"contexto": contexto, "fonte": fonte}
    except Exception as e:
        print(f"[PESQUISA] ERRO: {e}")
        return None


# ============================================================================
# 4. DICIONÁRIO DE CONHECIMENTO (knowledge_base.json)
# ============================================================================
def carregar_conhecimento() -> dict:
    """Carrega o dicionário de conhecimento existente (ou cria vazio)."""
    if os.path.exists(KNOWLEDGE_BASE_FILE):
        try:
            with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ knowledge_base.json corrompido ({e}); recriando...")
    return {}


def salvar_conhecimento(base: dict) -> None:
    """Salva o dicionário de conhecimento em disco."""
    with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)


def obter_contexto(topic: str, pergunta: str, usar_pesquisa: bool,
                   base: dict) -> tuple[str, str]:
    """
    Retorna (contexto, fonte) para o tópico.
    1. Verifica o knowledge_base.json primeiro.
    2. Se não achou e a pesquisa está ativa, busca na web e salva o novo fato.
    """
    chave = topic.strip().lower()
    if not usar_pesquisa:
        return "", ""

    # 1. Cache do dicionário
    if chave in base:
        return base[chave].get("contexto", ""), base[chave].get("fonte", "")

    # 2. Pesquisa na web
    resultado = pesquisar_web(pergunta)
    if not resultado:
        return "", ""

    base[chave] = {
        "topico": topic,
        "contexto": resultado["contexto"],
        "fonte": resultado.get("fonte", ""),
        "data": datetime.now().isoformat(timespec="seconds"),
    }
    salvar_conhecimento(base)
    log(f"🧠 Novo fato salvo no dicionário: '{topic}'")
    return resultado["contexto"], resultado.get("fonte", "")


# ============================================================================
# 4.5 VISUALIZAÇÃO DE PROGRESSO (barras de percentual + contagem regressiva)
# ============================================================================
_DISPOSITIVO: str | None = None


def _detectar_dispositivo() -> str:
    """Detecta se há GPU (via torch). CPU exige timeouts mais generosos."""
    global _DISPOSITIVO
    if _DISPOSITIVO is None:
        try:
            import torch
            _DISPOSITIVO = "gpu" if torch.cuda.is_available() else "cpu"
        except Exception:
            _DISPOSITIVO = "cpu"
    return _DISPOSITIVO


def _barra_percentual(pct: float, largura: int = 10) -> str:
    """Barra ASCII de percentual: 50% -> '[█████-----]'"""
    pct = max(0.0, min(100.0, pct))
    preenchidos = int(round(largura * pct / 100.0))
    return "[" + "█" * preenchidos + "-" * (largura - preenchidos) + "]"


def _contagem_regressiva(segundos: float, mensagem: str = "Aguardando") -> None:
    """
    Mostra uma contagem regressiva VISÍVEL (barra + segundos restantes).
    Se zerar sem resultado, sabemos que algo travou — nada de escuridão.
    """
    if segundos <= 0:
        return
    fim = time.time() + segundos
    with tqdm(total=segundos, unit="s", leave=False, bar_format="{desc}") as barra:
        while True:
            restante = fim - time.time()
            if restante <= 0:
                break
            pct = 100.0 * (1.0 - restante / segundos)
            barra.set_description(f"⏳ {mensagem} {_barra_percentual(pct)} {pct:3.0f}% | "
                                  f"falta {restante:4.1f}s")
            barra.refresh()
            time.sleep(0.1)
        barra.set_description(f"⏳ {mensagem} {_barra_percentual(100)} 100% — prosseguindo")
        barra.refresh()


def _post_com_progresso(url: str, payload: dict, timeout: int,
                        desc: str = "Ollama") -> tuple[requests.Response | None, Exception | None]:
    """
    Faz um POST em THREAD separada mostrando, enquanto espera, uma barra de
    percentual + contagem regressiva do tempo disponível. Se o tempo zerar sem
    resposta, sabemos que deu timeout (e o chamador ESCALA o tempo na tentativa
    seguinte, em vez de descartar a resposta).
    Retorna (resposta, erro).
    """
    resultado: dict = {}

    def _worker():
        try:
            resultado["resp"] = requests.post(url, json=payload, timeout=timeout)
        except Exception as e:
            resultado["erro"] = e

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    inicio = time.time()
    with tqdm(total=timeout, unit="s", leave=False, bar_format="{desc}") as barra:
        while thread.is_alive():
            decorrido = time.time() - inicio
            if decorrido >= timeout:
                break  # segurança extra (o worker também tem timeout próprio)
            pct = decorrido / timeout * 100.0
            restante = timeout - decorrido
            barra.set_description(f"⏳ {desc} {_barra_percentual(pct)} {pct:3.0f}% | "
                                  f"falta {restante:3.0f}s")
            barra.refresh()
            time.sleep(0.2)
        barra.set_description(f"⏳ {desc} {_barra_percentual(100)} 100% — aguardando resposta")
        barra.refresh()

    if "resp" in resultado:
        return resultado["resp"], None
    return None, resultado.get("erro", TimeoutError(f"timeout após {timeout}s"))


# ============================================================================
# 5. INTEGRAÇÃO COM OLLAMA (timeout adaptativo + retry com backoff exponencial)
# ============================================================================
def _chamar_ollama_api_chat(model: str, pergunta: str, sistema: str,
                            temperature: float, max_tokens: int = MAX_TOKENS,
                            timeout: int = OLLAMA_TIMEOUT) -> tuple[str, bool]:
    """
    Chama /api/chat do Ollama com barra de progresso e timeout configurável.
    Retorna (texto, cortada).
    `cortada=True` = bateu no limite de tokens (done_reason == "length"),
    ou seja, resposta cortada no meio do raciocínio.
    Em timeout/falha de rede, PROPAGA a exceção para o retry escalar o tempo.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": pergunta},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    resp, erro = _post_com_progresso(f"{OLLAMA_URL}/api/chat", payload, timeout,
                                     desc=f"Ollama {model}")
    if erro:
        raise erro
    if resp is None or resp.status_code != 200:
        return "", False
    data = resp.json()
    texto = (data.get("message") or {}).get("content", "").strip()
    # "length" = estourou o num_predict (resposta INCOMPLETA, cortada no meio)
    cortada = data.get("done_reason") == "length"
    return texto, cortada


def _chamar_ollama_api_generate(model: str, pergunta: str, sistema: str,
                                temperature: float, max_tokens: int = MAX_TOKENS,
                                timeout: int = OLLAMA_TIMEOUT) -> tuple[str, bool]:
    """Fallback usando /api/generate (com prompt composto). Retorna (texto, cortada)."""
    prompt = f"{sistema}\n\nUsuário: {pergunta}\n\nRigel:"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    resp, erro = _post_com_progresso(f"{OLLAMA_URL}/api/generate", payload, timeout,
                                     desc=f"Ollama {model} (fallback)")
    if erro:
        raise erro
    if resp is None or resp.status_code != 200:
        return "", False
    data = resp.json()
    texto = data.get("response", "").strip()
    cortada = data.get("done_reason") == "length"
    return texto, cortada


def gerar_resposta(model: str, pergunta: str, sistema: str,
                   temperature: float, max_tokens: int = MAX_TOKENS) -> tuple[str, bool]:
    """
    Gera uma resposta do Ollama com RETRY ADAPTATIVO:

    - TIMEOUT ESCALÁVEL: começa em OLLAMA_TIMEOUT (120s) e, a cada tentativa,
      sobe (x2) até OLLAMA_TIMEOUT_MAX (600s). Assim, CPU lenta não é descartada
      só por falta de tempo — nada de fallback por timeout insuficiente.
    - CPU/GPU: em CPU o tempo inicial é multiplicado por OLLAMA_TIMEOUT_CPU_FATOR.
    - TEMPERATURA VARIÁVEL: cada tentativa reinicia com um leve ajuste de
      temperatura (parâmetro diferente), em vez de repetir igual e falhar.
    - Cada chamada mostra barra de percentual + contagem regressiva.

    Retorna (texto, cortada).
    """
    ultimo_erro = None
    # CPU é mais lenta: aplica margem no tempo inicial
    base = OLLAMA_TIMEOUT
    if _detectar_dispositivo() == "cpu":
        base = int(base * OLLAMA_TIMEOUT_CPU_FATOR)
    timeout_atual = base

    for tentativa in range(1, OLLAMA_RETRIES + 1):
        # Reinicia com um contexto de geração levemente diferente
        temp_efetiva = min(1.0, temperature + (tentativa - 1) * 0.05)
        try:
            texto, cortada = _chamar_ollama_api_chat(model, pergunta, sistema,
                                                     temp_efetiva, max_tokens,
                                                     timeout_atual)
            if not texto:
                texto, cortada = _chamar_ollama_api_generate(model, pergunta, sistema,
                                                             temp_efetiva, max_tokens,
                                                             timeout_atual)
            if texto:
                return texto, cortada
            ultimo_erro = "resposta vazia"
        except requests.exceptions.Timeout as e:
            ultimo_erro = f"timeout de {timeout_atual}s ({e.__class__.__name__})"
        except requests.exceptions.RequestException as e:
            ultimo_erro = e
        except Exception as e:
            ultimo_erro = e

        # Escala o timeout para a próxima tentativa (CPU/GPU têm ritmos diferentes)
        novo_timeout = min(int(timeout_atual * OLLAMA_TIMEOUT_ESCALA), OLLAMA_TIMEOUT_MAX)
        if novo_timeout > timeout_atual:
            print(f"⚠️ Ollama lento ({ultimo_erro}). Tentativa {tentativa}/{OLLAMA_RETRIES}: "
                  f"timeout {timeout_atual}s → {novo_timeout}s")
        timeout_atual = novo_timeout

        if tentativa < OLLAMA_RETRIES:
            espera = OLLAMA_BACKOFF_BASE * (2 ** (tentativa - 1))
            _contagem_regressiva(espera, f"Reiniciando com tempo maior (tentativa {tentativa + 1})")

    print(f"❌ Ollama falhou após {OLLAMA_RETRIES} tentativas: {ultimo_erro}")
    return "", False


# ============================================================================
# 6. PONTUAÇÃO E PENALIDADE (QUALIDADE)
# ============================================================================
def _regra_ouro(texto: str) -> bool:
    """Regra de Ouro: termina com pergunta contextual oferecendo 2 opções."""
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    ultima = frases[-1].strip() if frases else ""
    if not ultima.endswith("?"):
        return False
    u = ultima.lower()
    # Pergunta de aprofundamento com 2 opções: 'ou', 'prefere', 'opções', 'gostaria de saber'
    return any(marca in u for marca in [" ou ", "prefere", "opções", "opcoes", "gostaria de saber", "quer saber", "preferiria"])


def _truncado(texto: str, min_tamanho: int = 60) -> bool:
    """Detecta resposta truncada, curta demais ou com caracteres estranhos.

    min_tamanho: limite mínimo de caracteres. Respostas informativas usam 60;
    saudações naturais (conversa curta) usam 20 (ex: 'Oi! Tudo bem por aqui?')
    para não serem confundidas com resposta truncada.
    """
    t = texto.strip()
    if len(t) < min_tamanho:
        return True
    # Termina sem pontuação final (corte no meio)
    if not re.search(r"[.!?…\"'”)]$", t):
        return True
    # Termina com reticências
    if t.endswith("..."):
        return True
    # Caracteres estranhos / mojibake
    if "ï¿½" in t or "�" in t:
        return True
    # Palavra repetida 3+ vezes seguidas
    palavras = t.lower().split()
    for i in range(len(palavras) - 2):
        if palavras[i] == palavras[i + 1] == palavras[i + 2]:
            return True
    return False


def _usou_contexto(texto: str, contexto: str) -> bool:
    """Verifica se a resposta aproveitou o contexto (datas, nomes, números)."""
    if not contexto:
        return False
    # Datas/anos concretos
    if re.search(r"\b(19|20)\d{2}\b", texto):
        return True
    # Palavras-chave do contexto (substantivos próprios ou termos longos)
    palavras_ctx = set(re.findall(r"\b[A-ZÀ-Ú][a-zà-ú]{3,}\b", contexto))
    for w in palavras_ctx:
        if w.lower() in texto.lower():
            return True
    # Números/percentuais concretos
    if re.search(r"\d+(?:[.,]\d+)?\s*%", texto):
        return True
    return False


def avaliar_resposta(texto: str, contexto: str, cortada: bool = False,
                     exigir_regra_ouro: bool = True) -> tuple[float, list[str]]:
    """
    Avalia a resposta com critérios objetivos e retorna (nota 0-10, motivos).

    ⚠️ REGRA DE OURO É OBRIGATÓRIA (em respostas informativas): sem a pergunta
    contextual de 2 opções no final, a nota é travada em SCORE_SEM_REGRA (3.0),
    abaixo do limiar padrão (4.0). Isso garante que respostas ruins NUNCA
    contaminem o dataset.

    ✅ SAUDAÇÕES são ISENTAS da Regra de Ouro (exigir_regra_ouro=False): um
    simples 'Oi! Tudo bem por aqui, e com você?' é natural e aceito.

    ⚠️ RESPOSTA CORTADA (cortada=True): quando o Ollama informa done_reason==\"length\",
    a resposta foi cortada no meio pelo limite de tokens — sem início/meio/fim.
    Essas respostas também são travadas (nunca entram no dataset).
    """
    motivos = []
    nota = BASE_SCORE
    texto = (texto or "").strip()
    tem_regra = _regra_ouro(texto)

    # 0. Resposta cortada pelo limite de tokens (incompleta) — BLOQUEANTE
    if cortada:
        motivos.append("🚫 RESPOSTA CORTADA (incompleta)")

    # 1. Regra de Ouro (+3) — OBRIGATÓRIA (exceto saudações)
    if tem_regra:
        nota += 3
        motivos.append("+3 regra de ouro")
    else:
        motivos.append("🚫 SEM REGRA DE OURO" if exigir_regra_ouro else "0 saudação natural (sem regra)")

    # 2. Fuga de IA (-2)
    t_low = texto.lower()
    if any(f in t_low for f in FRASES_FUGA_IA):
        nota -= 2
        motivos.append("-2 fuga de IA")
    else:
        motivos.append("0 sem fuga de IA")

    # 3. Genérico (-3)
    if any(f in t_low for f in FRASES_GENERICAS):
        nota -= 3
        motivos.append("-3 genérico")
    else:
        motivos.append("0 sem genérico")

    # 4. Alucinação/Truncamento (-4)
    #    Saudações são curtas por natureza — limite menor para não confundir
    #    uma conversa natural com resposta cortada no meio.
    if _truncado(texto, min_tamanho=(60 if exigir_regra_ouro else 20)):
        nota -= 4
        motivos.append("-4 truncado/estranho")
    else:
        motivos.append("0 sem truncamento")

    # 5. Uso de contexto (+2)
    if _usou_contexto(texto, contexto):
        nota += 2
        motivos.append("+2 usou contexto")
    else:
        motivos.append("0 sem contexto")

    # Travamento final: sem a Regra de Ouro (quando OBRIGATÓRIA) OU cortada,
    # a nota nunca passa do limiar. Saudações são isentas.
    if (not tem_regra and exigir_regra_ouro) or cortada:
        nota = min(nota, SCORE_SEM_REGRA)

    return max(0.0, min(10.0, nota)), motivos


# ============================================================================
# 7. SALVAMENTO E CACHE DE PERGUNTAS
# ============================================================================
def hash_pergunta(pergunta: str) -> str:
    return hashlib.md5(pergunta.strip().lower().encode("utf-8")).hexdigest()


def carregar_perguntas_existentes(output: str) -> set[str]:
    """Carrega os hashes das perguntas já salvas (arquivo + shards *_NNNN.jsonl)."""
    hashes = set()
    arquivos = [output]
    diretorio = os.path.dirname(output) or "."
    base_nome = os.path.basename(os.path.splitext(output)[0])
    ext = os.path.splitext(output)[1]
    try:
        for nome in os.listdir(diretorio):
            if nome.startswith(base_nome) and nome.endswith(ext):
                arquivos.append(os.path.join(diretorio, nome))
    except Exception:
        pass
    for caminho in arquivos:
        if not os.path.exists(caminho):
            continue
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                for linha in f:
                    try:
                        obj = json.loads(linha)
                        for m in obj.get("messages", []):
                            if m.get("role") == "user":
                                hashes.add(hash_pergunta(m.get("content", "")))
                    except Exception:
                        continue
        except Exception:
            pass
    return hashes


def salvar_exemplo(output: str, sistema: str, pergunta: str, resposta: str) -> None:
    """Escreve um exemplo aprovado no arquivo JSONL (append imediato)."""
    exemplo = {
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": pergunta},
            {"role": "assistant", "content": resposta},
        ],
        "_id": hashlib.md5(f"{pergunta}|{resposta}".encode("utf-8")).hexdigest()[:16],
        "_idioma": "pt-BR",
        "_data": datetime.now().isoformat(timespec="seconds"),
    }
    with open(output, "a", encoding="utf-8") as f:
        f.write(json.dumps(exemplo, ensure_ascii=False) + "\n")


def normalizar_lexica(texto: str) -> str:
    """
    Normalização leve para deduplicação SEMÂNTICA aproximada:
    minúsculas, sem pontuação e tokens ordenados — captura paráfrases
    de ordem como 'Quem foi Tiradentes?' e 'Tiradentes, quem foi?'.
    """
    tokens = re.findall(r"[a-zà-ú0-9]+", texto.lower())
    return " ".join(sorted(set(tokens)))


def carregar_perguntas_norm_existentes(output: str) -> set[str]:
    """Carrega as chaves lexicais das perguntas já salvas (dedup semântica leve)."""
    chaves = set()
    diretorio = os.path.dirname(output) or "."
    base_nome = os.path.basename(os.path.splitext(output)[0])
    ext = os.path.splitext(output)[1]
    arquivos = [output]
    try:
        for nome in os.listdir(diretorio):
            if nome.startswith(base_nome) and nome.endswith(ext):
                arquivos.append(os.path.join(diretorio, nome))
    except Exception:
        pass
    for caminho in arquivos:
        if not os.path.exists(caminho):
            continue
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                for linha in f:
                    try:
                        obj = json.loads(linha)
                        for m in obj.get("messages", []):
                            if m.get("role") == "user":
                                chaves.add(normalizar_lexica(m.get("content", "")))
                    except Exception:
                        continue
        except Exception:
            pass
    return chaves


def avaliar_com_juiz(judge_model: str, pergunta: str, resposta: str,
                     min_score: float) -> tuple[bool, float, str]:
    """
    Usa um modelo juiz (maior) para avaliar a resposta além das heurísticas.
    Retorna (aprovada, nota, motivo). Em falha, retorna (True, 0.0, motivo)
    para NUNCA bloquear a geração por causa do juiz.
    """
    try:
        prompt = (f"Pergunta do usuário: {pergunta}\n\n"
                  f"Resposta do assistente:\n{resposta}\n\n"
                  f"{JUDGE_PROMPT}")
        texto, _ = _chamar_ollama_api_chat(judge_model, prompt,
                                           "Você é um avaliador imparcial de qualidade.",
                                           temperature=0.0)
        if not texto:
            return True, 0.0, "juiz não respondeu (fallback heurístico)"
        m = re.search(r"\{.*\}", texto, re.DOTALL)
        if not m:
            return True, 0.0, "juiz sem JSON (fallback heurístico)"
        dados = json.loads(m.group(0))
        nota = float(dados.get("nota", 0.0))
        aprovada = bool(dados.get("aprovada", nota >= min_score))
        motivo = str(dados.get("motivo", ""))[:120]
        return aprovada, nota, motivo
    except Exception as e:
        print(f"[JUIZ] Falha ({e}); usando apenas heurísticas.")
        return True, 0.0, "juiz indisponível"


def salvar_checkpoint(estado: dict) -> None:
    """Salva estado de progresso para retomar depois (--resume)."""
    estado["timestamp"] = datetime.now().isoformat(timespec="seconds")
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Não foi possível salvar checkpoint: {e}")


def carregar_checkpoint() -> dict | None:
    """Carrega o checkpoint salvo (ou None)."""
    if not os.path.exists(CHECKPOINT_FILE):
        return None
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ checkpoint.json inválido ({e}); começando do zero.")
        return None


def gerar_estatisticas_dataset(arquivos: list[str]) -> dict:
    """Calcula estatísticas básicas do dataset gerado (média de tokens, tamanho)."""
    stats: dict[str, float | int] = {"total_exemplos": 0, "total_tokens_user": 0,
                                     "total_tokens_assistant": 0, "tamanho_bytes": 0}
    for caminho in arquivos:
        if not os.path.exists(caminho):
            continue
        stats["tamanho_bytes"] += os.path.getsize(caminho)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                for linha in f:
                    try:
                        obj = json.loads(linha)
                        for m in obj.get("messages", []):
                            n = len(m.get("content", "").split())
                            if m.get("role") == "user":
                                stats["total_tokens_user"] += n
                            elif m.get("role") == "assistant":
                                stats["total_tokens_assistant"] += n
                        stats["total_exemplos"] += 1
                    except Exception:
                        continue
        except Exception:
            pass
    if stats["total_exemplos"]:
        stats["media_tokens_user"] = stats["total_tokens_user"] / stats["total_exemplos"]
        stats["media_tokens_assistant"] = stats["total_tokens_assistant"] / stats["total_exemplos"]
    return stats


def enriquecer_dataset(origem: str, model: str, output: str, delay: float,
                       temperatura: float, max_exemplos: int | None = None,
                       max_tokens: int = MAX_TOKENS) -> None:
    """
    Lê um dataset existente e REEscreve a resposta do assistant seguindo a
    Constituição do Rigel (system prompt fixo). Salva um novo arquivo JSONL.
    Respostas CORTADAS pelo limite de tokens são descartadas (incompletas).
    """
    criar_pastas()
    if not os.path.dirname(output):
        output = os.path.join(PASTA_JSONL, output)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    total = 0
    salvos = 0
    erros = 0
    cortadas = 0
    print("=" * 70)
    print(f"🧬 ENRIQUECENDO DATASET: {origem}")
    print(f"🤖 Modelo: {model} | Saída: {output}")
    print("=" * 70)
    try:
        for exemplo in ler_exemplos(origem):
            total += 1
            if max_exemplos and salvos >= max_exemplos:
                break
            msgs = exemplo["messages"]
            user_txt = next((m["content"] for m in msgs if m["role"] == "user"), "")
            if not user_txt:
                erros += 1
                continue
            nova, cortada = gerar_resposta(model, user_txt, SYSTEM_PROMPT, temperatura,
                                           max_tokens=max_tokens)
            if not nova:
                erros += 1
                continue
            if cortada:
                # Resposta incompleta (bateu no limite de tokens) — não usar
                cortadas += 1
                continue
            novo_exemplo = {"messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_txt},
                {"role": "assistant", "content": nova},
            ]}
            with open(output, "a", encoding="utf-8") as f:
                f.write(json.dumps(novo_exemplo, ensure_ascii=False) + "\n")
            salvos += 1
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        print("\n⏹️ Enriquecimento interrompido. Progresso salvo.")

    print("\n" + "=" * 70)
    print("📊 ENRIQUECIMENTO CONCLUÍDO")
    print(f"✅ Exemplos reescritos: {salvos} / {total}")
    print(f"✂️ Descartados por corte: {cortadas}")
    print(f"❌ Erros: {erros}")
    print(f"📄 Saída: {output}")
    print("=" * 70)


# ============================================================================
# 8. DOWNLOAD, EXTRAÇÃO E EXPLOSÃO DE DATASETS EXTERNOS
# ============================================================================
def criar_pastas() -> None:
    """Garante a existência da estrutura de pastas do projeto."""
    for p in [PASTA_BASE, PASTA_RAW, PASTA_GERADOS, PASTA_JSONL]:
        os.makedirs(p, exist_ok=True)


def nome_arquivo_de_url(url: str) -> str:
    """Extrai o nome do arquivo de uma URL (remove query string)."""
    path = unquote(urlparse(url).path)
    nome = os.path.basename(path)
    return nome or "download.bin"


def baixar_arquivo(url: str, destino_dir: str) -> str | None:
    """
    Baixa um arquivo de uma URL para destino_dir com barra de progresso.
    Retorna o caminho completo do arquivo baixado, ou None em caso de erro.
    """
    os.makedirs(destino_dir, exist_ok=True)
    nome = nome_arquivo_de_url(url)
    caminho = os.path.join(destino_dir, nome)
    try:
        resp = requests.get(url, stream=True, timeout=120,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(caminho, "wb") as f:
            with tqdm(total=total, unit="B", unit_scale=True,
                      desc=f"📥 {nome}", dynamic_ncols=True) as barra:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        barra.update(len(chunk))
        tamanho = os.path.getsize(caminho)
        log(f"📥 Baixado: {caminho} ({tamanho / 1024 / 1024:.1f} MB)")
        return caminho
    except Exception as e:
        log(f"❌ Falha ao baixar {url}: {e}")
        return None


def extrair_arquivo(arquivo: str, destino_dir: str) -> list[str]:
    """
    Extrai um arquivo .zip / .tar / .tar.gz / .tgz / .gz para destino_dir.
    Retorna a lista de arquivos extraídos (ou [] se não for comprimido).
    """
    os.makedirs(destino_dir, exist_ok=True)
    extraidos: list[str] = []
    nome_low = os.path.basename(arquivo).lower()

    try:
        if nome_low.endswith(".zip"):
            with zipfile.ZipFile(arquivo, "r") as z:
                z.extractall(destino_dir)
                extraidos = [os.path.join(destino_dir, n) for n in z.namelist()
                             if not n.endswith("/")]
        elif nome_low.endswith((".tar.gz", ".tgz")):
            with tarfile.open(arquivo, "r:gz") as t:
                t.extractall(destino_dir)
                extraidos = [os.path.join(destino_dir, m.name) for m in t.getmembers()
                             if m.isfile()]
        elif nome_low.endswith(".tar"):
            with tarfile.open(arquivo, "r:") as t:
                t.extractall(destino_dir)
                extraidos = [os.path.join(destino_dir, m.name) for m in t.getmembers()
                             if m.isfile()]
        elif nome_low.endswith(".gz"):
            base_nome = os.path.basename(arquivo)
            saida = os.path.join(destino_dir,
                                 base_nome[:-3] if base_nome.lower().endswith(".gz") else base_nome)
            with gzip.open(arquivo, "rb") as fin, open(saida, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            extraidos = [saida]
        else:
            return []  # não é um arquivo comprimido

        log(f"📦 Extraídos {len(extraidos)} arquivos para {destino_dir}")
        return extraidos
    except Exception as e:
        log(f"❌ Falha ao extrair {arquivo}: {e}")
        return []


def _corrigir_mojibake(texto: str) -> str:
    """Corrige mojibake (UTF-8 lido como Latin-1/CP1252): 'VocÃª' -> 'Você'."""
    if not texto:
        return texto
    if not re.search(r'Ã.|Â.|â€|â€™|â€œ', texto):
        return texto
    for encoding in ('latin-1', 'cp1252'):
        try:
            tentativa = texto.encode(encoding, errors='strict').decode('utf-8', errors='strict')
            if '\ufffd' not in tentativa:
                return tentativa
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return texto


# ============================================================================
# PORTÃO DE QUALIDADE PT-BR (regra de ouro 05/08): todo dataset baixado passa
# pelo sanitizador ao explodir — corrige mojibake por ocorrência e remove
# caracteres fora do ABNT2 (100% português brasileiro). Fallback: _corrigir_mojibake.
# ============================================================================
try:
    from sanitizador_ptbr import corrigir_mojibake_inteligente, remover_invalidos
    _TEM_SANITIZADOR = True
except Exception:
    _TEM_SANITIZADOR = False


def _sanitizar_conteudo_ptbr(texto: str) -> str:
    """Aplica o portão de qualidade a um conteúdo: mojibake inteligente +
    remoção de caracteres fora do ABNT2. Pode retornar string vazia (o chamador
    decide descartar)."""
    if not texto:
        return texto
    if _TEM_SANITIZADOR:
        limpo = corrigir_mojibake_inteligente(texto)
        limpo, _n = remover_invalidos(limpo)
        return limpo.strip()
    return _corrigir_mojibake(texto).strip()


def _listar_conversas(obj: dict):
    """Retorna a lista de turnos de um dataset (messages/conversations/conversa/chat),
    aceitando LISTA ou STRING JSON (ex.: dataset Guará). Retorna None se não achar."""
    for chave in ("messages", "conversations", "conversa", "conversation", "chat"):
        valor = obj.get(chave)
        if isinstance(valor, list):
            return valor
        if isinstance(valor, str):
            try:
                parsed = json.loads(valor)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                continue
    return None


def normalizar_exemplo(obj) -> dict | None:
    """
    Converte um objeto JSON de qualquer dataset para o formato Rigel:
    {"messages": [{"role": ..., "content": ...}, ...]}
    Suporta: 'messages', 'conversations' (HuggingFace, lista OU string JSON), 'chat'.
    Retorna None se não for possível.
    """
    if not isinstance(obj, dict):
        return None

    msgs = None
    if isinstance(obj.get("messages"), list):
        msgs = obj["messages"]
    else:
        conv = _listar_conversas(obj)
        if conv is not None:
            # Formato HuggingFace: {"from": "human"/"gpt", "value": "..."}
            msgs = []
            for item in conv:
                if isinstance(item, str):
                    # Turno como string simples (ex.: lista de textos alternados)
                    papel = "assistant" if len(msgs) % 2 == 1 else "user"
                    msgs.append({"role": papel, "content": item.strip()})
                    continue
                if not isinstance(item, dict):
                    continue
                de = str(item.get("from", "") or item.get("role", "")).lower()
                if de in ("human", "user", "h", "usuario", "pessoa"):
                    papel = "user"
                elif de in ("gpt", "assistant", "assistente", "bot", "model", "a"):
                    papel = "assistant"
                else:
                    papel = None
                valor = item.get("value") or item.get("content") or item.get("text")
                if papel and valor:
                    msgs.append({"role": papel, "content": str(valor).strip()})

    if not msgs:
        return None

    # Valida e normaliza as mensagens (com correção de mojibake)
    limpas = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        papel = str(m.get("role", "")).lower()
        if papel not in ("system", "user", "assistant"):
            continue
        conteudo = _sanitizar_conteudo_ptbr(str(m.get("content", "")).strip())
        if not conteudo:
            continue
        limpas.append({"role": papel, "content": conteudo})

    if len(limpas) < 2:
        return None
    # Garante system no início (usa o fixo do Rigel se não houver)
    if limpas[0]["role"] != "system":
        limpas.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    return {"messages": limpas}


def normalizar_exemplo_causal(obj) -> dict | None:
    """Converte um objeto de PRÉ-TREINO (campo 'text'/'content') para o formato causal.

    Diferente do SFT (messages), aqui mantemos o texto corrido — o `treino.py`
    (causal) aceita o campo `text`. Metadados úteis (source/subset) são mantidos.
    Retorna None se não houver texto utilizável.
    """
    if not isinstance(obj, dict):
        return None
    # Só atua em objetos SEM conversas (senão o SFT já cuida)
    if isinstance(obj.get("messages"), list) or _listar_conversas(obj) is not None:
        return None
    texto = obj.get("text")
    if not isinstance(texto, str) or not texto.strip():
        texto = obj.get("content")
        if not isinstance(texto, str) or not texto.strip():
            return None
    texto = _sanitizar_conteudo_ptbr(texto.strip())
    if not texto:
        return None
    return {
        "text": texto,
        "source": obj.get("source") or "",
        "subset": obj.get("subset") or "",
    }


def ler_exemplos(origem: str):
    """
    Gerador que lê e normaliza exemplos de um arquivo JSONL/JSON (ou .gz).
    """
    def _parse_linhas(f):
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
            except Exception:
                continue
            if isinstance(obj, list):  # linha pode ser uma lista de exemplos
                for item in obj:
                    e = normalizar_exemplo(item) or normalizar_exemplo_causal(item)
                    if e:
                        yield e
            else:
                e = normalizar_exemplo(obj) or normalizar_exemplo_causal(obj)
                if e:
                    yield e

    if origem.endswith(".gz"):
        with gzip.open(origem, "rt", encoding="utf-8") as f:
            yield from _parse_linhas(f)
    elif origem.endswith(".jsonl"):
        with open(origem, "r", encoding="utf-8") as f:
            yield from _parse_linhas(f)
    elif origem.endswith(".json"):
        with open(origem, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, list):
            for item in dados:
                e = normalizar_exemplo(item)
                if e:
                    yield e
        else:
            e = normalizar_exemplo(dados)
            if e:
                yield e


def localizar_arquivos_dataset(pasta: str) -> list[str]:
    """Localiza arquivos .jsonl/.json/.gz dentro de uma pasta (recursivo)."""
    arquivos = []
    for raiz, _, arquivos_nome in os.walk(pasta):
        for nome in arquivos_nome:
            if nome.endswith((".jsonl", ".json", ".jsonl.gz", ".json.gz")):
                arquivos.append(os.path.join(raiz, nome))
    return sorted(arquivos)


def _pasta_destino_split(base: str, nome: str, indice_pasta: int) -> str:
    """Pasta destino: a PRIMEIRA leva vai na RAIZ do dataset (sem pasta_001);
    só se passar de MAX_FILES_POR_PASTA é que cria pasta_002, pasta_003...
    Assim os arquivos ficam direto em dados/gerados/jsonl/<nome>/."""
    sub = "" if indice_pasta == 1 else f"pasta_{indice_pasta:03d}"
    pasta = os.path.join(base, nome, sub)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _detectar_tipo_exemplo(obj) -> str:
    """Classifica o formato de um exemplo (para diagnóstico de falha de explosão)."""
    if not isinstance(obj, dict):
        return "nao_dict"
    if isinstance(obj.get("messages"), list):
        return "messages"
    if _listar_conversas(obj) is not None:
        return "conversas"
    if obj.get("text") or obj.get("content"):
        return "pre_treino_texto"
    if obj.get("prompt") or obj.get("instruction") or obj.get("pergunta"):
        return "instrucao"
    return "desconhecido"


def _diagnosticar_falha_explosao(origem: str) -> dict:
    """Investiga POR QUE um dataset gerou 0 exemplos na explosão.

    Lê uma amostra do arquivo de origem, classifica o formato predominante e
    devolve motivo + sugestão (procedimento lógico, não apenas '0 exemplos').
    """
    import collections

    tipos = collections.Counter()
    amostra_chaves = None
    linhas_lidas = 0
    try:
        eh_gz = str(origem).endswith(".gz")
        abrir = gzip.open if eh_gz else open
        modo = "rt" if eh_gz else "r"
        with abrir(origem, modo, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    obj = json.loads(linha)
                except Exception:
                    continue
                if isinstance(obj, list):
                    obj = obj[0] if obj else None
                if not isinstance(obj, dict):
                    continue
                if amostra_chaves is None:
                    amostra_chaves = list(obj.keys())
                tipos[_detectar_tipo_exemplo(obj)] += 1
                linhas_lidas += 1
                if linhas_lidas >= 50:
                    break
    except FileNotFoundError:
        return {"tipo": "arquivo_inexistente",
                "motivo": f"Arquivo não encontrado: {origem}",
                "sugestao": "O download não gerou o arquivo intermediário. Refaça o download."}
    except Exception as e:
        return {"tipo": "erro_leitura", "motivo": str(e),
                "sugestao": "Arquivo corrompido ou sem permissão de leitura."}

    if linhas_lidas == 0:
        return {"tipo": "arquivo_vazio",
                "motivo": "Nenhuma linha JSON válida foi lida no arquivo.",
                "sugestao": "O download gerou arquivo vazio/corrompido. Refaça o download."}

    principal = tipos.most_common(1)[0][0] if tipos else "desconhecido"
    mapa = {
        "pre_treino_texto": (
            "Dataset é de PRÉ-TREINO (campo 'text'/'content' = texto corrido), sem conversas (messages).",
            "A explosão agora suporta CAUSAL (preserva o campo text, aceito pelo treino.py). "
            "Se mesmo assim der 0 exemplos, confira se há textos não vazios no arquivo."),
        "instrucao": (
            "Dataset usa formato de instrução (prompt/instruction), não messages de conversa.",
            "Ajuste o normalizador para este formato ou escolha dataset com messages."),
        "messages": (
            "Dataset tem 'messages', mas os exemplos foram descartados na validação "
            "(roles inválidos ou conteúdo vazio).",
            "Confira se as mensagens têm roles system/user/assistant e conteúdo não vazio."),
        "conversas": (
            "Dataset tem conversas, mas a normalização descartou tudo (roles ou conteúdo inválidos).",
            "Confira o formato dos turnos (from/value, role/content)."),
        "desconhecido": (
            "Formato de exemplo não reconhecido (chaves: %s)." % ", ".join(amostra_chaves or []),
            "Reveja a estrutura do dataset; pode ser necessário suporte a novo formato."),
    }
    motivo, sugestao = mapa.get(principal, ("Motivo desconhecido.", "Investigue o arquivo de origem."))
    return {"tipo": principal, "motivo": motivo, "sugestao": sugestao,
            "chaves_amostra": amostra_chaves, "linhas_amostradas": linhas_lidas,
            "distribuicao": dict(tipos)}


def explodir_dataset(origem: str, nome: str, max_exemplos: int | None = None,
                     max_files: int = MAX_FILES_POR_PASTA,
                     exemplos_por_arquivo: int = EXEMPLOS_POR_ARQUIVO,
                     on_progresso=None, total_estimado: int = 0,
                     on_diagnostico=None, deve_continuar=None, on_evento=None):
    """
    Lê um dataset (arquivo ou pasta), normaliza, deduplica e explode em arquivos
    JSONL de `exemplos_por_arquivo` exemplos, com no máximo `max_files` arquivos
    por pasta (pasta_001, pasta_002, ...) dentro de dados/gerados/jsonl/<nome>/.
    on_progresso(processados, total_estimado) é chamado periodicamente.
    Retorna (total_exemplos, total_arquivos, total_pastas).
    """
    if os.path.isdir(origem):
        arquivos = localizar_arquivos_dataset(origem)
        if not arquivos:
            log(f"⚠️ Nenhum arquivo JSONL/JSON encontrado em {origem}")
            return 0, 0, 0
        log(f"📂 {len(arquivos)} arquivos de origem em {origem}")
    else:
        arquivos = [origem]

    # Estima o total de exemplos (linhas) para a barra de progresso
    if on_progresso and not total_estimado:
        for arq in arquivos:
            try:
                # Arquivo GRANDE: não conta linhas (evita ler tudo 2x — protege o SSD)
                if os.path.getsize(arq) > 300 * 1024 * 1024:
                    continue
                if arq.endswith(".gz"):
                    with gzip.open(arq, "rt", encoding="utf-8") as f:
                        total_estimado += sum(1 for _ in f)
                else:
                    with open(arq, "r", encoding="utf-8") as f:
                        total_estimado += sum(1 for _ in f)
            except Exception:
                pass

    total_exemplos = 0
    total_arquivos = 0      # contador GERAL de arquivos escritos
    arquivos_pasta = 0      # contador dentro da pasta atual
    total_pastas = 1
    duplicatas = 0
    vistos: set[str] = set()
    buf: list[dict] = []
    pasta_atual = _pasta_destino_split(PASTA_JSONL, nome, 1)

    def _flush():
        nonlocal total_arquivos, arquivos_pasta, total_pastas, pasta_atual
        if not buf:
            return
        if arquivos_pasta >= max_files:
            total_pastas += 1
            pasta_atual = _pasta_destino_split(PASTA_JSONL, nome, total_pastas)
            arquivos_pasta = 0
        idx = arquivos_pasta + 1
        caminho = os.path.join(pasta_atual, f"{nome}_{idx:05d}.jsonl")
        with open(caminho, "w", encoding="utf-8") as f:
            for e in buf:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        arquivos_pasta += 1
        total_arquivos += 1
        buf.clear()
        if on_evento:
            on_evento("arquivo", caminho)

    try:
        for arquivo in arquivos:
            for exemplo in ler_exemplos(arquivo):
                if deve_continuar is not None and not deve_continuar():
                    log("⏸️ Explosão interrompida por controle externo (pausar/parar).")
                    break
                if max_exemplos and total_exemplos >= max_exemplos:
                    break
                # Dedup pela pergunta do usuário (só para SFT messages; causal não tem user)
                chave = None
                if "messages" in exemplo:
                    for m in exemplo["messages"]:
                        if m["role"] == "user":
                            chave = hash_pergunta(m["content"])
                            break
                if chave:
                    if chave in vistos:
                        duplicatas += 1
                        continue
                    vistos.add(chave)
                total_exemplos += 1
                buf.append(exemplo)
                if on_progresso and (total_exemplos % 50 == 0 or total_exemplos == total_estimado):
                    on_progresso(total_exemplos, total_estimado)
                if len(buf) >= exemplos_por_arquivo:
                    _flush()
            if max_exemplos and total_exemplos >= max_exemplos:
                break
            if deve_continuar is not None and not deve_continuar():
                break
        _flush()
    except KeyboardInterrupt:
        log("⏹️ Explosão interrompida pelo usuário (dados já salvos).")

    if on_progresso:
        on_progresso(total_exemplos, total_estimado)

    # Diagnóstico: 0 exemplos = falha de explosão (formato incompatível, vazio, etc.)
    if total_exemplos == 0 and on_diagnostico:
        try:
            diag = _diagnosticar_falha_explosao(origem)
            diag["dataset"] = nome
            on_diagnostico(diag)
            log(f"❌ Dataset '{nome}': 0 exemplos — diagnóstico: {diag.get('tipo')} | {diag.get('motivo')}")
        except Exception as e:
            on_diagnostico({"tipo": "erro_diagnostico", "dataset": nome,
                            "motivo": str(e), "sugestao": "Falha ao diagnosticar a explosão."})
            log(f"⚠️ Erro ao diagnosticar '{nome}': {e}")

    log(f"✅ Dataset '{nome}': {total_exemplos} exemplos, {total_arquivos} arquivos, "
        f"{total_pastas} pastas, {duplicatas} duplicatas removidas")
    if on_evento:
        on_evento("fim", f"{total_exemplos} exemplos, {total_arquivos} arquivos, "
                          f"{total_pastas} pastas, {duplicatas} duplicatas removidas")
    return total_exemplos, total_arquivos, total_pastas


def _converter_local_para_jsonl(pasta_repo: str, caminho_saida: str,
                                max_total: int | None = None,
                                on_progresso=None) -> str | None:
    """Converte arquivos locais baixados (parquet/json/jsonl/csv) para JSONL.

    on_progresso(processados, total) reporta o andamento da conversão
    (em exemplos). Retorna o caminho do JSONL gerado, ou None.
    """
    from datasets import load_dataset
    arquivos = sorted(os.listdir(pasta_repo))
    parquets = [os.path.join(pasta_repo, f) for f in arquivos if f.endswith(".parquet")]
    jsons = [os.path.join(pasta_repo, f) for f in arquivos if f.endswith((".json", ".jsonl"))]
    csvs = [os.path.join(pasta_repo, f) for f in arquivos if f.endswith(".csv")]
    builder, dados = None, None
    if parquets:
        builder, dados = "parquet", parquets
    elif jsons:
        builder, dados = "json", jsons
    elif csvs:
        builder, dados = "csv", csvs
    if not builder:
        return None
    try:
        ds = load_dataset(builder, data_files=dados, split="train")
    except Exception:
        return None
    # Tenta descobrir o total de exemplos (para %); fallback: progresso indefinido
    total = None
    try:
        total = len(ds)
    except Exception:
        total = None
    if on_progresso:
        on_progresso(0, total)
    with open(caminho_saida, "w", encoding="utf-8") as f:
        for i, exemplo in enumerate(ds):
            if max_total and i >= max_total:
                break
            f.write(json.dumps(dict(exemplo), ensure_ascii=False) + "\n")
            if on_progresso and (i % 500 == 0 or (total and i + 1 >= total)):
                on_progresso(i + 1, total)
    if on_progresso:
        on_progresso(i + 1, total)
    return caminho_saida


def baixar_huggingface(repo_id: str, destino_dir: str, on_progresso=None,
                       on_progresso_conversao=None,
                       max_total: int | None = None) -> str | None:
    """
    Baixa um dataset do HuggingFace para destino_dir.
    Ordem: snapshot_download (com % de bytes) + conversão local → datasets.load_dataset
    (streaming) → snapshot simples → URL direta.
    on_progresso(mb_baixados, mb_totais, pct) reporta o progresso de bytes (0-100).
    on_progresso_conversao(processados, total) reporta o progresso da conversão
    local para JSONL (em exemplos).
    Retorna a pasta/arquivo processável, ou None.
    """
    os.makedirs(destino_dir, exist_ok=True)
    nome_repo = repo_id.replace("/", "_")
    pasta_repo = os.path.join(destino_dir, nome_repo)
    hf_token = os.environ.get("HF_TOKEN") or None

    # 0) Pré-checagem: dataset gated exige token — falha rápido e claro
    try:
        resp = requests.get(f"https://huggingface.co/api/datasets/{repo_id}", timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 (RigelSLM Dashboard)"})
        if resp.status_code == 200:
            info = resp.json()
            if info.get("gated") and not hf_token:
                log(f"🔒 Dataset '{repo_id}' é GATED (exige login HF). "
                    f"Defina a variável de ambiente HF_TOKEN para baixar.")
                return None
    except Exception:
        pass

    # 1) snapshot_download COM progresso de bytes + conversão local
    if on_progresso:
        try:
            from huggingface_hub import snapshot_download
            from tqdm import tqdm as _TqBase
            class _Tq(_TqBase):
                def update(self, n=1):
                    super().update(n)
                    if self.total and on_progresso:
                        on_progresso(self.n / (1024 * 1024), self.total / (1024 * 1024),
                                     min(100, int(self.n * 100 / self.total)))
            log(f"🤗 Baixando '{repo_id}' (com progresso de bytes)...")
            snapshot_download(repo_id=repo_id, repo_type="dataset", local_dir=pasta_repo,
                              token=hf_token, tqdm_class=_Tq)  # type: ignore[arg-type]
            if on_progresso:
                on_progresso(0, 0, 100)
            caminho = os.path.join(pasta_repo, "dataset.jsonl")
            convertido = _converter_local_para_jsonl(pasta_repo, caminho, max_total=max_total,
                                                     on_progresso=on_progresso_conversao)
            if convertido:
                log(f"🤗 Dataset convertido para JSONL em {convertido}")
                return convertido
            log(f"⚠️ Nenhum arquivo parquet/json/csv encontrado em {pasta_repo}.")
        except Exception as e:
            log(f"⚠️ snapshot+conversão falhou ({e}); tentando datasets/load_dataset...")

    # 2) Tenta datasets.load_dataset (streaming) — sem % de bytes, mas funciona p/ todos
    try:
        from datasets import load_dataset
        log(f"🤗 Baixando HuggingFace '{repo_id}' via datasets (streaming)...")
        dataset = load_dataset(repo_id, split="train", streaming=True, token=hf_token)
        caminho = os.path.join(pasta_repo, "dataset.jsonl")
        os.makedirs(pasta_repo, exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            for i, exemplo in enumerate(dataset):
                if max_total and i >= max_total:
                    break
                f.write(json.dumps(dict(exemplo), ensure_ascii=False) + "\n")
        log(f"🤗 Dataset salvo em {caminho}")
        return caminho
    except Exception as e:
        log(f"⚠️ datasets falhou ({e}), tentando snapshot_download...")

    # 3) Tenta huggingface_hub.snapshot_download (sem progresso)
    try:
        from huggingface_hub import snapshot_download
        log("🤗 Baixando via snapshot_download...")
        snapshot_download(repo_id=repo_id, repo_type="dataset", local_dir=pasta_repo, token=hf_token)
        return pasta_repo
    except Exception as e:
        log(f"⚠️ snapshot_download falhou ({e}), tentando URL direta...")

    # 4) URL direta de arquivos comuns
    for nome_tentativa in ("train.jsonl", "dataset.jsonl", "data.jsonl"):
        url = f"https://huggingface.co/datasets/{repo_id}/resolve/main/{nome_tentativa}"
        caminho = baixar_arquivo(url, pasta_repo)
        if caminho:
            return caminho
    log(f"❌ Não foi possível baixar '{repo_id}' do HuggingFace.")
    return None


def _nome_rigel_jsonl_da_hora() -> str:
    """Convenção Rigel: dataset BAIXADO de fora recebe nome próprio do sistema."""
    return f"rigeljsonl_{datetime.now().strftime('%Y%m%d_%H%M')}"


def processar_download(url_download: str | None, hf_repo: str | None,
                       pasta_processar: str | None, arquivo_extrair: str | None,
                       nome: str | None, max_total: int | None,
                       max_files: int, exemplos_por_arquivo: int) -> None:
    """
    Modo de processamento externo: baixa (URL/HF), extrai e explode o dataset
    em pastas de no máximo `max_files` arquivos dentro de dados/gerados/jsonl/.
    """
    criar_pastas()
    origem = None
    nome_origem = nome

    if arquivo_extrair:
        # Apenas extrair um arquivo local para dados/raw/
        destino = os.path.join(PASTA_RAW,
                               os.path.splitext(os.path.basename(arquivo_extrair))[0])
        extrair_arquivo(arquivo_extrair, destino)
        origem = destino
        nome_origem = nome_origem or os.path.basename(destino)

    elif url_download:
        arquivo = baixar_arquivo(url_download, PASTA_RAW)
        if not arquivo:
            log("❌ Download falhou. Nada a processar.")
            return
        base_nome = os.path.splitext(os.path.basename(arquivo))[0]
        destino = os.path.join(PASTA_RAW, base_nome)
        extraidos = extrair_arquivo(arquivo, destino)
        origem = destino if extraidos else arquivo
        # Convenção Rigel: baixado de fora -> nome próprio do sistema
        nome_origem = nome_origem or _nome_rigel_jsonl_da_hora()

    elif hf_repo:
        origem = baixar_huggingface(hf_repo, PASTA_RAW)
        if not origem:
            log("❌ Download HuggingFace falhou. Nada a processar.")
            return
        # Convenção Rigel: baixado de fora -> nome próprio do sistema
        nome_origem = nome_origem or _nome_rigel_jsonl_da_hora()

    elif pasta_processar:
        origem = pasta_processar
        if not os.path.exists(origem):
            log(f"❌ Pasta/arquivo não encontrado: {origem}")
            return
        nome_origem = nome_origem or os.path.splitext(
            os.path.basename(origem.rstrip("/\\")))[0]

    if not origem:
        log("❌ Nenhuma origem de processamento informada.")
        return

    nome_origem = nome_origem or "dataset"
    log(f"🚀 EXPLODINDO DATASET: {origem}")
    explodir_dataset(origem, nome_origem, max_exemplos=max_total,
                     max_files=max_files, exemplos_por_arquivo=exemplos_por_arquivo)


# ============================================================================
# 9. FUNÇÃO PRINCIPAL
# ============================================================================
def main():
    """
    FLUXO DO COMANDO `python createjsonl.py` (modo geração, sem argumentos):

      [1] Lê os argumentos da linha de comando (ou usa os padrões:
          500 exemplos, modelo gemma2:2b na CPU ou qwen2.5:7b com --gpu,
          saída dataset_rigel.jsonl).

      [2] Decide o MODO de operação:
            --enrich                                    -> reescreve respostas
            --download / --hf-dataset / --process / --extract -> baixa/explode
            (nenhum destes)                             -> GERAÇÃO (fluxo abaixo)

      [3] PREPARAÇÃO:
            - Cria pastas (dados/raw, dados/gerados/jsonl)
            - Carrega knowledge_base.json (memória de fatos já pesquisados)
            - Carrega perguntas já salvas no arquivo (evita repetir)

      [4] LOOP até completar --count exemplos aprovados:
            a. Escolhe categoria/assunto BALANCEADOS (via categories.py)
            b. Monta uma pergunta variada (prefixos + templates)
            c. Dedup: exato (MD5) + semântico leve (ordem de palavras)
            d. Busca contexto: dicionário OU pesquisa web (DuckDuckGo)
            e. Gera 2 respostas com o Ollama (temp 0.7 e 0.9)
            f. Pontua as duas (0-10) e escolhe a melhor (vencedora)
            g. (Opcional) Modelo juiz reavalia a vencedora
            h. Se nota >= --min-score -> SALVA no JSONL (append imediato)
            i. Atualiza contadores de balanceamento + checkpoint

      [5] RESUMO FINAL: salvos, descartados, estatísticas e distribuição.
    """
    parser = argparse.ArgumentParser(
        description="Gera dataset JSONL para Fine-Tuning SFT do RigelSLM "
                    "(Pesquisa + Dicionário + Pontuação)"
    )
    parser.add_argument("--model", type=str, default=None,
                        help="Modelo no Ollama. Default automático: "
                             f"{MODELO_CPU_PADRAO} (CPU) ou {MODELO_GPU_PADRAO} (--gpu). "
                             "NÃO use 'rigelslm' (modelo em treinamento).")
    parser.add_argument("--count", type=int, default=500,
                        help="Número de exemplos a gerar (default: 500)")
    parser.add_argument("--output", type=str, default="dataset_rigel.jsonl",
                        help="Arquivo de saída JSONL (default: dataset_rigel.jsonl)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Delay entre requisições em segundos (default: 1.5)")
    parser.add_argument("--no-search", action="store_true", default=False,
                        help="Desabilita busca web e dicionário (usa apenas o modelo local)")
    parser.add_argument("--temperature-high", type=float, default=0.9,
                        help="Temperatura da 2ª variação (default: 0.9)")
    parser.add_argument("--temperature-low", type=float, default=0.7,
                        help="Temperatura da 1ª variação (default: 0.7)")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS,
                        help=f"Limite máximo de tokens por resposta (default: {MAX_TOKENS}). "
                             f"Respostas que estouram este limite são descartadas (incompletas).")
    parser.add_argument("--download", type=str, default=None,
                        help="URL de dataset (.jsonl/.zip/.tar.gz) para baixar, extrair e explodir")
    parser.add_argument("--hf-dataset", type=str, default=None,
                        help="Dataset do HuggingFace (ex: org/nome) para baixar e explodir")
    parser.add_argument("--process", type=str, default=None,
                        help="Pasta ou arquivo JSONL/JSON existente para normalizar e explodir")
    parser.add_argument("--extract", type=str, default=None,
                        help="Apenas extrai um arquivo .zip/.tar.gz/.gz para dados/raw/")
    parser.add_argument("--nome", type=str, default=None,
                        help="Nome da pasta de saída do dataset explodido")
    parser.add_argument("--max-files", type=int, default=MAX_FILES_POR_PASTA,
                        help=f"Máximo de arquivos por pasta (default: {MAX_FILES_POR_PASTA})")
    parser.add_argument("--examples-per-file", type=int, default=EXEMPLOS_POR_ARQUIVO,
                        help=f"Exemplos por arquivo JSONL (default: {EXEMPLOS_POR_ARQUIVO})")
    parser.add_argument("--max-total", type=int, default=None,
                        help="Limite máximo total de exemplos a processar (segurança)")
    parser.add_argument("--min-score", type=float, default=4.0,
                        help="Nota mínima para salvar um exemplo (default: 4.0). "
                             "Sem a Regra de Ouro a nota é travada em 3.0, então "
                             "por padrão ela é obrigatória. Use 0.0 para ser leniente.")
    parser.add_argument("--judge-model", type=str, default=None,
                        help="Modelo juiz (ex: llama3.2:3b) para avaliar a qualidade "
                             "além das heurísticas (opcional)")
    parser.add_argument("--resume", action="store_true", default=False,
                        help="Retoma do último checkpoint (contadores de categoria)")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Testa o fluxo completo sem salvar nada")
    parser.add_argument("--enrich", type=str, default=None,
                        help="Dataset existente (JSONL/JSON) para reescrever as respostas "
                             "seguindo a Constituição do Rigel (enriquecimento)")
    parser.add_argument("--gpu", action="store_true", default=False,
                        help="Modo GPU (ex: Colab): usa o modelo padrão de GPU "
                             f"({MODELO_GPU_PADRAO}) em vez do modelo de CPU")
    parser.add_argument("--usar-topicos-txt", action="store_true", default=False,
                        help=("Usa também os tópicos de topicos.txt (fonte RSS/dashboard) "
                              f"como assuntos: ~{TOPICOS_TXT_CHANCE:.0%} dos exemplos, "
                              "após filtragem das manchetes").replace("%", "%%"))
    args = parser.parse_args()

    # ---- Resolve o modelo padrão por dispositivo ----
    if args.model is None:
        args.model = MODELO_GPU_PADRAO if args.gpu else MODELO_CPU_PADRAO

    # ---- Alerta: nunca usar o modelo em TREINAMENTO para gerar dados ----
    if args.model.lower().startswith("rigelslm"):
        print("⚠️⚠️  ATENÇÃO: você escolheu o modelo 'rigelslm'.")
        print("   Ele é o modelo em TREINAMENTO (ainda muito novinho).")
        print("   Usá-lo para gerar o dataset pode ensinar respostas ruins ao Rigel.")
        print(f"   Recomendado: {MODELO_CPU_PADRAO} (CPU) ou {MODELO_GPU_PADRAO} (GPU).")
        print()

    if args.count <= 0:
        parser.error("--count deve ser maior que 0")
    if not (0.0 <= args.temperature_low <= 1.0) or not (0.0 <= args.temperature_high <= 1.0):
        parser.error("Temperaturas devem estar entre 0.0 e 1.0")
    if not (0.0 <= args.min_score <= 10.0):
        parser.error("--min-score deve estar entre 0.0 e 10.0")
    if args.max_files <= 0:
        parser.error("--max-files deve ser maior que 0")
    if args.examples_per_file <= 0:
        parser.error("--examples-per-file deve ser maior que 0")

    # ---- Modo enriquecimento de dataset existente ----
    if args.enrich:
        enriquecer_dataset(args.enrich, args.model, args.output, args.delay,
                           args.temperature_low, max_exemplos=args.max_total,
                           max_tokens=args.max_tokens)
        return

    # ---- Modo processamento externo (download / huggingface / processar / extrair) ----
    if args.download or args.hf_dataset or args.process or args.extract:
        processar_download(
            url_download=args.download,
            hf_repo=args.hf_dataset,
            pasta_processar=args.process,
            arquivo_extrair=args.extract,
            nome=args.nome,
            max_total=args.max_total,
            max_files=args.max_files,
            exemplos_por_arquivo=args.examples_per_file,
        )
        return

    usar_pesquisa = not args.no_search

    # ---- Saída padrão: pasta jsonlocal/ com nome DATADO ----------------
    #      (datasets de dias/máquinas diferentes NÃO se sobrescrevem)
    criar_pastas()
    if not os.path.dirname(args.output):
        data_hoje = datetime.now().strftime("%Y%m%d")
        args.output = os.path.join(PASTA_JSONL, "jsonlocal", f"rigel_{data_hoje}.jsonl")
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # ---- Inicialização ----
    log("=" * 70)
    log(f"🚀 CREATEJSONL v1.0.0 - GERADOR DE DATASET SFT PARA O RIGELSLM")
    log(f"📅 {datetime.now()}")
    log(f"🤖 Modelo: {args.model} | Exemplos: {args.count}"
        + (" | [MODO GPU]" if args.gpu else " | [MODO CPU]") )
    log(f"📁 Saída: {args.output} | Delay: {args.delay}s")
    log(f"💻 Dispositivo: {_detectar_dispositivo().upper()}"
        + (" — timeouts mais generosos (CPU)" if _detectar_dispositivo() == "cpu" else ""))
    log(f"⏱️ Timeout: {OLLAMA_TIMEOUT}s inicial, escala x{OLLAMA_TIMEOUT_ESCALA:.1f} "
        f"até {OLLAMA_TIMEOUT_MAX}s")
    log(f"🌐 Pesquisa web: {'ATIVA' if usar_pesquisa else 'DESATIVADA (--no-search)'}")
    log(f"🌡️ Temperaturas: {args.temperature_low} / {args.temperature_high}")
    log(f"🎯 Nota mínima: {args.min_score} (Regra de Ouro é obrigatória)")
    if args.judge_model:
        log(f"🧑⚖️ Modelo juiz: {args.judge_model}")
    if args.usar_topicos_txt:
        log(f"📄 Tópicos externos: ATIVO ({TOPICOS_TXT_FILE}, ~{TOPICOS_TXT_CHANCE:.0%} "
            f"dos exemplos, manchetes filtradas)")
    if args.dry_run:
        log(f"🧪 MODO DRY-RUN: nenhum arquivo será salvo")
    if args.resume:
        log(f"♻️ Modo resume ativado (checkpoint: {CHECKPOINT_FILE})")
    log("=" * 70)

    conhecimento = carregar_conhecimento() if usar_pesquisa else {}
    log(f"🧠 Dicionário de conhecimento carregado: {len(conhecimento)} tópicos")

    cache_perguntas = carregar_perguntas_existentes(args.output)
    cache_norm = carregar_perguntas_norm_existentes(args.output)
    log(f"🗂️ Perguntas já existentes no arquivo: {len(cache_perguntas)}")

    # Tópicos externos (topicos.txt): carrega uma vez, antes do loop
    topicos_externos: list[str] = []
    if args.usar_topicos_txt:
        topicos_externos = carregar_topicos_externos_filtrados()
        log(f"📄 Tópicos externos carregados de {TOPICOS_TXT_FILE}: "
            f"{len(topicos_externos)} aproveitáveis")

    salvos = 0
    descartados = {"pontuacao": 0, "erro": 0, "duplicata": 0, "vazio": 0,
                   "regra_ouro": 0, "juiz": 0, "cortada": 0}
    vitorias = {f"temp_{args.temperature_low}": 0, f"temp_{args.temperature_high}": 0}
    contadores_categoria: dict[str, int] = {}

    # Retomada do checkpoint (contadores de categoria)
    if args.resume:
        ckpt = carregar_checkpoint()
        if ckpt:
            contadores_categoria = ckpt.get("contadores", {}) or {}
            log(f"♻️ Checkpoint carregado: {ckpt.get('salvos', 0)} exemplos anteriores, "
                f"{len(contadores_categoria)} categorias")

    # Controle de sharding (vários arquivos, um por vez)
    arquivo_atual = args.output
    exemplos_no_arquivo = 0
    arquivos_gerados = [args.output]

    # ---- Loop principal ----
    try:
        barra = tqdm(total=args.count, desc="Gerando exemplos", unit="ex",
                     unit_scale=False, dynamic_ncols=True)
        tentativas = 0
        # Loop principal: gera até `--count` exemplos APROVADOS.
        # O limite `count * 3` é uma trava de segurança: se o modelo estiver
        # descartando tudo (ex: não cumpre a Regra de Ouro), o script para
        # sozinho em vez de rodar para sempre.
        while salvos < args.count and tentativas < args.count * 3:
            tentativas += 1

            # [a] Monta uma pergunta: categoria/assunto balanceados de categories.py
            #     ~SAUDACAO_CHANCE% das vezes é uma SAUDAÇÃO natural (conversa curta).
            #     Com --usar-topicos-txt, ~TOPICOS_TXT_CHANCE% usa topicos.txt.
            pergunta, categoria, assunto = gerar_pergunta(contadores_categoria,
                                                          topicos_externos)
            eh_saudacao = (categoria == "saudacao")
            exigir_regra = not eh_saudacao

            # [c] DEDUP EXATO: pergunta idêntica (MD5) já usada? pula.
            ch = hash_pergunta(pergunta)
            if ch in cache_perguntas:
                descartados["duplicata"] += 1
                continue
            cache_perguntas.add(ch)

            # [c] DEDUP SEMÂNTICO LEVE: paráfrases como
            #     'Quem foi Tiradentes?' vs 'Tiradentes, quem foi?' são iguais.
            ch_norm = normalizar_lexica(pergunta)
            if ch_norm in cache_norm:
                descartados["duplicata"] += 1
                continue
            cache_norm.add(ch_norm)

            # [d] CONTEXTO: primeiro olha no dicionário (knowledge_base.json);
            #     se não achar, pesquisa na web (DuckDuckGo) e salva o novo fato.
            #     Saudações NÃO fazem busca na web (seria desperdício).
            contexto = ""
            fonte = ""
            if usar_pesquisa and not eh_saudacao:
                contexto, fonte = obter_contexto(
                    topic=assunto,
                    pergunta=pergunta,
                    usar_pesquisa=True,
                    base=conhecimento,
                )

            # [e] GERA 2 RESPOSTAS com temperaturas diferentes (variação).
            #     `cortada` = True quando o Ollama estourou o limite de tokens
            #     (resposta incompleta — nunca deve entrar no dataset).
            r1, cortada1 = gerar_resposta(args.model, pergunta, SYSTEM_PROMPT,
                                          args.temperature_low, max_tokens=args.max_tokens)
            if args.delay > 0:
                time.sleep(args.delay)
            r2, cortada2 = gerar_resposta(args.model, pergunta, SYSTEM_PROMPT,
                                          args.temperature_high, max_tokens=args.max_tokens)
            if args.delay > 0:
                time.sleep(args.delay)

            if not r1 and not r2:
                # As duas falharam (Ollama fora/sobrecarregado): conta erro e segue.
                descartados["erro"] += 1
                barra.update(0)
                continue
            if not r1 or not r2:
                # Uma falhou: usa a que funcionou (sem competição).
                resposta = r1 or r2
                cortada = cortada1 or cortada2
                vencedor = f"temp_{args.temperature_low}" if r1 else f"temp_{args.temperature_high}"
                nota, motivos = avaliar_resposta(resposta, contexto, cortada=cortada,
                                                 exigir_regra_ouro=exigir_regra)
                vitorias[vencedor] += 1
            else:
                # [f] PONTUA as duas (0-10) e fica com a MELHOR.
                nota1, motivos1 = avaliar_resposta(r1, contexto, cortada=cortada1,
                                                   exigir_regra_ouro=exigir_regra)
                nota2, motivos2 = avaliar_resposta(r2, contexto, cortada=cortada2,
                                                   exigir_regra_ouro=exigir_regra)
                if nota2 > nota1:
                    resposta, nota, motivos, vencedor = r2, nota2, motivos2, f"temp_{args.temperature_high}"
                else:
                    resposta, nota, motivos, vencedor = r1, nota1, motivos1, f"temp_{args.temperature_low}"
                vitorias[vencedor] += 1

            # [h] LIMIAR DE QUALIDADE: nota abaixo do mínimo não entra no dataset.
            #     Sem a Regra de Ouro (quando obrigatória) a nota é travada em 3.0.
            #     Saudações são isentas da Regra de Ouro (não são rejeitadas por isso).
            #     Respostas CORTADAS pelo limite de tokens também são travadas.
            if nota < args.min_score:
                if "CORTADA" in " ".join(motivos):
                    descartados["cortada"] += 1
                elif not _regra_ouro(resposta) and exigir_regra:
                    descartados["regra_ouro"] += 1
                else:
                    descartados["pontuacao"] += 1
                tqdm.write(f"   🗑️ Descartada (nota {nota:.1f}) - {', '.join(motivos)}")
                continue

            # [g] MODELO JUIZ (opcional): reavalia a vencedora além das heurísticas.
            nota_juiz = None
            motivo_juiz = ""
            if args.judge_model:
                aprovada_juiz, nota_juiz, motivo_juiz = avaliar_com_juiz(
                    args.judge_model, pergunta, resposta, args.min_score)
                if not aprovada_juiz:
                    descartados["juiz"] += 1
                    tqdm.write(f"   🧑⚖️ Juiz reprovou (nota {nota_juiz:.1f}): {motivo_juiz}")
                    continue

            contadores_categoria[categoria] = contadores_categoria.get(categoria, 0) + 1

            pergunta_log = pergunta[:90] + ("..." if len(pergunta) > 90 else "")

            if args.dry_run:
                # Modo teste: não grava nada, apenas simula
                salvos += 1
                barra.update(1)
                barra.set_postfix(salvos=salvos, nota=f"{nota:.1f}", vencedor=vencedor)
                tqdm.write(f"   🧪 [DRY-RUN] Salvaria #{salvos}/{args.count}\n"
                           f"      ❓ {pergunta_log}\n"
                           f"      🏷️ {categoria} | nota {nota:.1f} | {', '.join(motivos)}")
                continue

            # Sharding: abre um novo arquivo ao atingir o limite de exemplos por arquivo
            if exemplos_no_arquivo >= args.examples_per_file:
                base, ext = os.path.splitext(args.output)
                arquivo_atual = f"{base}_{len(arquivos_gerados) + 1:04d}{ext}"
                exemplos_no_arquivo = 0
                arquivos_gerados.append(arquivo_atual)
            salvar_exemplo(arquivo_atual, SYSTEM_PROMPT, pergunta, resposta)
            exemplos_no_arquivo += 1
            salvos += 1
            barra.update(1)
            barra.set_postfix(salvos=salvos, nota=f"{nota:.1f}", vencedor=vencedor)
            log(f"✅ Exemplo {salvos}/{args.count} salvo\n"
                f"   ❓ {pergunta_log}\n"
                f"   🏷️ {categoria} | vencedor: {vencedor} | nota: {nota:.1f} | {', '.join(motivos)}"
                + (f" | juiz: {nota_juiz:.1f} ({motivo_juiz})" if nota_juiz is not None else "")
                + (f" | fonte: {fonte[:60]}" if fonte else ""))

            # Checkpoint periódico (retomada segura)
            if salvos % 5 == 0:
                salvar_checkpoint({"salvos": salvos, "contadores": contadores_categoria})

        barra.close()
    except KeyboardInterrupt:
        print("\n⏹️ Interrompido pelo usuário. Progresso já salvo no arquivo.")
        if not args.dry_run:
            salvar_checkpoint({"salvos": salvos, "contadores": contadores_categoria})
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        if not args.dry_run:
            salvar_checkpoint({"salvos": salvos, "contadores": contadores_categoria})

    # ---- Resumo final ----
    if usar_pesquisa:
        salvar_conhecimento(conhecimento)

    print("\n" + "=" * 70)
    print("📊 RESUMO FINAL")
    print("=" * 70)
    print(f"✅ Total de exemplos salvos:      {salvos}")
    print(f"🚫 Descartados sem Regra de Ouro: {descartados['regra_ouro']}")
    print(f"✂️ Descartados por corte (tokens): {descartados['cortada']}")
    print(f"🗑️ Descartados por pontuação:     {descartados['pontuacao']}")
    print(f"🧑‍⚖️ Descartados pelo juiz:        {descartados['juiz']}")
    print(f"❌ Descartados por erro:          {descartados['erro']}")
    print(f"🔁 Descartados por duplicata:     {descartados['duplicata']}")
    print(f"📄 Arquivos gerados:              {len(arquivos_gerados)}")
    print(f"🏆 Vitórias por temperatura:       {vitorias}")
    if args.usar_topicos_txt:
        print(f"📄 Exemplos com tópicos externos:  "
              f"{contadores_categoria.get(CATEGORIA_EXTERNA, 0)}")
    print(f"🧠 Dicionário de conhecimento:    {len(conhecimento)} tópicos "
          f"({KNOWLEDGE_BASE_FILE})")

    if not args.dry_run:
        stats = gerar_estatisticas_dataset(arquivos_gerados)
        print("-" * 70)
        print("📈 ESTATÍSTICAS DO DATASET")
        print(f"   Exemplos totais (no arquivo): {stats['total_exemplos']}")
        print(f"   Média tokens (user):          {stats.get('media_tokens_user', 0):.0f}")
        print(f"   Média tokens (assistant):     {stats.get('media_tokens_assistant', 0):.0f}")
        print(f"   Tamanho total:                {stats['tamanho_bytes'] / 1024:.1f} KB")
        print(f"   Distribuição por categoria (top 10):")
        for cat, qtd in sorted(contadores_categoria.items(), key=lambda x: -x[1])[:10]:
            print(f"     • {cat}: {qtd}")
    print("=" * 70)


if __name__ == "__main__":
    main()
