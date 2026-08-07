#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================================
# limpeza_leve_rigel_v2.py — Pipeline LEVE de limpeza de datasets para SLMs
# ============================================================================
# INSTALAÇÃO (rodar UMA vez):
#   pip install ftfy beautifulsoup4 fasttext datasketch datasets
#
# MODELO DE IDIOMA (fasttext lid.176.bin) — baixa automático se não existir:
#   https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
#   (ou passe o caminho com --lid-model)
#
# USO:
#   python limpeza_leve_rigel_v2.py --origem dados/raw --saida dados/processed
#   python limpeza_leve_rigel_v2.py --origem dados/raw/arquivo.jsonl --saida dados/processed
#   python limpeza_leve_rigel_v2.py --origem dados/raw --saida dados/processed --max-docs 1000   # teste
#
# SAÍDA (pasta --saida):
#   rigel_sft.parquet       — exemplos com estrutura ChatML (messages) → SFT
#   rigel_pretrain.parquet  — texto corrido puro → Pré-Treinamento Contínuo
#   limpeza_relatorio.json  — contadores e avisos (não fica perdido)
#
# PRINCÍPIO (regra de ouro do usuário): texto corrido NUNCA vira diálogo
# artificial (isso ensina o modelo a ecoar). QA estruturado vira ChatML.
# Streaming do início ao fim — RAM constante, mesmo com milhões de arquivos.
# ============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Optional

# ============================================================================
# DEPENDÊNCIAS OPCIONAIS (carregadas sob demanda — degrade sem quebrar)
# ============================================================================
try:
    import ftfy  # noqa: F401
    _TEM_FTFY = True
except Exception:
    _TEM_FTFY = False

try:
    from bs4 import BeautifulSoup
    _TEM_BS4 = True
except Exception:
    _TEM_BS4 = False

try:
    import fasttext
    _TEM_FASTTEXT = True
except Exception:
    _TEM_FASTTEXT = False

try:
    from datasketch import MinHash, MinHashLSH
    _TEM_DATASKETCH = True
except Exception:
    _TEM_DATASKETCH = False

try:
    from datasets import Dataset
    _TEM_DATASETS = True
except Exception:
    _TEM_DATASETS = False

# ============================================================================
# CONFIGURAÇÃO (evoluir aqui, sem mexer na lógica)
# ============================================================================
URL_LID = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"
LID_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "modelos", "lid.176.bin")

MIN_PALAVRAS = 20              # 2.2: documento com <20 palavras → descarta
MAX_LINHAS_DUP_RATIO = 0.30    # 2.2: >30% de linhas duplicadas → descarta
MAX_SIMBOLOS_RATIO = 0.10      # 2.2: >10% de símbolos incomuns → descarta
LIMIAR_MINHASH = 0.8           # 2.1: similaridade > 0.8 → duplicado aproximado
TAMANHO_MAX_LINHA = 500_000    # proteção: linha gigante = corrompida
NUM_PERM = 128                 # MinHash: número de permutações (128 é o padrão leve)
BATCH_FILTER = 512             # 2.7: batch do .filter() no modo streaming

# URLs soltas no meio do texto (2.4 — além do bs4)
_RE_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# Símbolos incomuns p/ o filtro de qualidade (2.2)
_SIMBOLOS = set("#*_<>{}[]|~^`\\")

# ============================================================================
# FILTRO DE RUÍDO DE IA (05/08 — datasets sintéticos vazam o "pensamento" do
# modelo gerador: "the user gave instructions", "we need to output the article",
# "final answer should be...", "Let's craft article..."). Isso é LIXO que não
# deve virar dado de treino — detectamos por padrões e descartamos.
# ============================================================================
_RUIIDO_IA_PADROES = [
    # Inglês (datasets sintéticos tipo Madras1 v2)
    r"the\s+user\s+gave\s+instructions",
    r"we\s+need\s+to\s+output\s+the\s+article",
    r"final\s+answer\s+should\s+be\s+the\s+article",
    r"let'?s\s+craft\s+an?\s+article",
    r"let'?s\s+produce\s+the\s+article",
    r"write\s+an\s+article\s+of\s+high\s+quality",
    r"write\s+a\s+long\s+consistent\s+text",
    r"no\s+extra\s+commentary\s+outside\s+article",
    r"there'?s\s+no\s+further\s+conversation",
    r"so\s+we\s+need\s+to\s+output",
    r"the\s+conversation\s*:\s*system\s+gave",
    r"we\s+need\s+a\s+long\s+consistent\s+text",
    r"opening\s+situates\s+reader",
    r"portuguese\s+brazilian\s+natural",
    r"produce\s+the\s+article\s+as\s+per\s+format",
    r"no\s+extra\s+observations",
    r"answer\s*:\s*they\s+asked\s+to\s+write",
    r"system\s+gave\s+instructions\s+to\s+write",
    r"let'?s\s+write\s+an\s+article",
    r"i'?ll\s+write\s+an\s+article",
    r"here'?s\s+an\s+article",
    r"as\s+an\s+ai\s+(language\s+model|assistant)",
    r"i\s+am\s+an\s+ai\s+(language\s+model|assistant)",
    r"i\s+can'?t\s+(access|browse|fetch)",
    r"i\s+don'?t\s+have\s+(access|information|the\s+ability)",
    r"my\s+knowledge\s+cutoff",
    r"as\s+a\s+large\s+language\s+model",
    # Português
    r"o\s+usu[áa]rio\s+deu\s+instru[çc][õo]es",
    r"precisamos\s+gerar\s+o\s+artigo",
    r"a\s+resposta\s+final\s+deve\s+ser\s+o\s+artigo",
    r"vamos\s+criar\s+um\s+artigo",
    r"escreva\s+um\s+artigo\s+de\s+alta\s+qualidade",
    r"sem\s+coment[áa]rios\s+extras",
    r"n[ãa]o\s+h[áa]\s+mais\s+conversa",
]
_RE_RUIDO_IA = [re.compile(p, re.IGNORECASE) for p in _RUIIDO_IA_PADROES]


def _tem_ruido_ia(texto: str) -> bool:
    """True se o texto contém padrões de "pensamento" de IA vazado (lixo)."""
    if not texto:
        return False
    t = texto[:3000].lower()
    for rx in _RE_RUIDO_IA:
        try:
            if rx.search(t):
                return True
        except Exception:
            continue
    return False

# Progresso AO VIVO (o dashboard/executor lê este arquivo p/ desenhar a barra)
# REGRA DE OURO 05/08: o usuário precisa VER porcentagem/contagem/tempo.
PROGRESSO_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "logs", "limpeza_progresso.json")

_progresso_atual: dict = {}


def _atualizar_progresso(**kwargs) -> None:
    """Grava logs/limpeza_progresso.json — o painel lê p/ a barra de %.

    Além do arquivo, imprime UMA linha no stdout com flush=True (o SSE do
    executor mostra movimento em tempo real).
    """
    global _progresso_atual
    _progresso_atual.update(kwargs)
    _progresso_atual["atualizado_em"] = time.strftime("%H:%M:%S")
    try:
        os.makedirs(os.path.dirname(PROGRESSO_LOG), exist_ok=True)
        with open(PROGRESSO_LOG, "w", encoding="utf-8") as _f:
            json.dump(_progresso_atual, _f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        pct = _progresso_atual.get("pct", 0)
        lidos = _progresso_atual.get("lidos", 0)
        sft = _progresso_atual.get("sft", 0)
        seg = _progresso_atual.get("decorrido_s", 0)
        print(f"⏳ {pct:5.1f}% | {lidos} lidos | SFT={sft} | {seg}s",
              flush=True)
    except Exception:
        pass
# Palavras típicas de Portugal (2.5 — heurística opcional PT-PT)
_PT_PT_HINTS = ("autocarro", "comboio", "telemóvel", "ecrã", "pulover",
                "peúgas", "frigorífico", "canadiana", "fatia", "casa de banho",
                "bairro", "estacionar", "peditório", "miúdo", "miúda",
                "sandes", "camião", "aeroporto", "autocarro", "rapariga",
                "rapaz", "moço", "fixe", "giro", "giro", "bué", "pronto")
# Palavras tipicamente BRASILEIRAS (2.5 — contrapeso para não errar)
_PT_BR_HINTS = ("você", "também", "a gente", "ônibus", "geladeira", "banheiro",
                "celular", "computador", "legal", "bacana", "moleque", "menina",
                "carro", "computador", "internet", "trabalho", "escola")

# ============================================================================
# CONSOLE UTF-8 (Windows cp1252 quebra com acentos/emoji)
# ============================================================================
def _reconfigurar_console() -> None:
    for _s in (sys.stdout, sys.stderr):
        _r = getattr(_s, "reconfigure", None)
        if callable(_r):
            try:
                _r(encoding="utf-8", errors="replace")
            except Exception:
                pass


_reconfigurar_console()


# ============================================================================
# ETAPA 0 — NORMALIZAÇÃO BÁSICA (chave de dedup exato + entrada da limpeza)
# ============================================================================
def _normalizar_chave(texto: str) -> str:
    """Texto normalizado para a chave de dedup EXATO (2.1).

    Normaliza espaço, unicode NFC, minúsculas — duas formas do mesmo texto
    (ex.: quebras de linha diferentes) colapsam para a MESMA chave.
    """
    t = texto or ""
    try:
        import unicodedata
        t = unicodedata.normalize("NFC", t)
    except Exception:
        pass
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _dedup_exato_chave(texto: str) -> str:
    """Hash md5 da chave normalizada (2.1 — dedup exato)."""
    return hashlib.md5(_normalizar_chave(texto).encode("utf-8")).hexdigest()


# ============================================================================
# ETAPA 1 — FILTRO DE IDIOMA (fasttext lid.176) — PRIMEIRO (2.3)
# ============================================================================
def _baixar_lid(destino: str) -> bool:
    """Baixa o modelo lid.176.bin se não existir. Retorna True se OK."""
    try:
        if os.path.exists(destino):
            return True
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        print(f"  ⬇️  Baixando modelo de idioma lid.176.bin (~126 MB)...")
        urllib.request.urlretrieve(URL_LID, destino)
        return os.path.exists(destino)
    except Exception as e:
        print(f"  ⚠️  Não consegui baixar lid.176.bin: {e}")
        return False


class _FiltroIdioma:
    """Filtro de idioma via fasttext lid.176 (2.1/2.3).

    Detecta 'pt' (fasttext não separa PT-BR de PT-PT — limitação documentada,
    ver 2.5). Se não houver fasttext, cai para langdetect (se instalado) ou
    aceita tudo com aviso.
    """

    def __init__(self, caminho_lid: str = ""):
        self._modelo = None
        self.disponivel = False
        self.aviso = ""
        self._caminho = caminho_lid or LID_PADRAO
        if _TEM_FASTTEXT:
            if _baixar_lid(self._caminho):
                try:
                    self._modelo = fasttext.load_model(self._caminho)
                    self.disponivel = True
                except Exception as e:
                    self.aviso = f"falha ao carregar lid.176.bin: {e}"
            else:
                self.aviso = "modelo lid.176.bin indisponível"
        else:
            try:
                import langdetect  # noqa: F401
                self.disponivel = True
                self._usar_langdetect = True
                self.aviso = "fasttext ausente — usando langdetect (mais lento)"
            except Exception:
                self.aviso = ("fasttext E langdetect ausentes — filtro de idioma "
                              "desligado (pip install fasttext langdetect)")

    def eh_portugues(self, texto: str) -> bool:
        """True se o texto é português (pt). None se indisponível → aceita."""
        if not self.disponivel:
            return True  # sem ferramenta → aceita (documentado no relatório)
        texto_teste = texto[:2000]  # amostra: suficiente p/ idioma
        try:
            if getattr(self, "_usar_langdetect", False):
                import langdetect
                try:
                    return langdetect.detect(texto_teste) in ("pt", "pt-br")
                except Exception:
                    return True  # texto curto demais → conservador
            pred = self._modelo.predict(texto_teste.replace("\n", " "))
            lingua = pred[0][0].replace("__label__", "") if pred and pred[0] else ""
            return lingua == "pt"
        except Exception:
            return True  # nunca derruba o pipeline por causa do idioma


# ============================================================================
# ETAPA 2 — LIMPEZA DE TEXTO (ftfy + bs4 + URLs) (2.4)
# ============================================================================
def _limpar_texto(texto: str) -> str:
    """Limpeza: mojibake (ftfy), HTML (bs4) e URLs soltas (regex)."""
    if not texto:
        return ""
    # 1) ftfy: corrige mojibake/encoding
    if _TEM_FTFY:
        try:
            texto = ftfy.fix_text(texto)
        except Exception:
            pass
    # 2) bs4: remove tags HTML
    if _TEM_BS4:
        try:
            texto = BeautifulSoup(texto, "html.parser").get_text(" ")
        except Exception:
            pass
    # 3) regex explícita de URLs (2.4 — bs4 não remove URLs soltas)
    texto = _RE_URL.sub(" ", texto)
    # 4) normaliza espaços
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


# ============================================================================
# ETAPA 3 — FILTRO DE QUALIDADE HEURÍSTICA (C4/Gopher simplificados) (2.2)
# ============================================================================
def _contar_simbolos_ratio(texto: str) -> float:
    if not texto:
        return 0.0
    total = len(texto)
    if total == 0:
        return 0.0
    n = sum(1 for ch in texto if ch in _SIMBOLOS)
    return n / total


def _linhas_duplicadas_ratio(texto: str) -> float:
    """Proporção de linhas repetidas (menus/rodapés de sites)."""
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    if len(linhas) <= 1:
        return 0.0
    vistos = set()
    dups = 0
    for l in linhas:
        if l in vistos:
            dups += 1
        else:
            vistos.add(l)
    return dups / len(linhas)


def _filtro_qualidade(texto: str) -> tuple[bool, str]:
    """(ok, motivo). Filtros C4/Gopher simplificados (2.2).

    Descarta se: <20 palavras, >30% linhas duplicadas, >10% símbolos.
    """
    if not texto or len(texto.strip()) == 0:
        return False, "vazio"
    n_palavras = len(texto.split())
    if n_palavras < MIN_PALAVRAS:
        return False, f"curto ({n_palavras} palavras < {MIN_PALAVRAS})"
    if _linhas_duplicadas_ratio(texto) > MAX_LINHAS_DUP_RATIO:
        return False, "linhas_duplicadas"
    if _contar_simbolos_ratio(texto) > MAX_SIMBOLOS_RATIO:
        return False, "simbolos_incomuns"
    return True, ""


# ============================================================================
# ETAPA 4 — DEDUP (exato md5 + aproximado MinHash) (2.1)
# ============================================================================
class _Deduplicador:
    """Dedup exato (md5) + aproximado (MinHash LSH, limiar > 0.8)."""

    def __init__(self, limiar: float = LIMIAR_MINHASH):
        self._vistos_exato: set[str] = set()
        self._lsh = MinHashLSH(threshold=limiar, num_perm=NUM_PERM) \
            if _TEM_DATASKETCH else None
        self._minhashes: dict[str, MinHash] = {}
        self.duplicados_exatos = 0
        self.duplicados_aprox = 0

    def _minhash_texto(self, texto: str) -> "MinHash | None":
        m = MinHash(num_perm=NUM_PERM)
        for token in re.findall(r"\w+", texto.lower()):
            m.update(token.encode("utf-8"))
        return m

    def eh_novo(self, texto: str) -> bool:
        """True se o texto NÃO é duplicado (exato ou aproximado)."""
        # Dedup exato (2.1) — barato, roda primeiro
        chave = _dedup_exato_chave(texto)
        if chave in self._vistos_exato:
            self.duplicados_exatos += 1
            return False
        self._vistos_exato.add(chave)

        # Dedup aproximado (2.1) — MinHash LSH
        if self._lsh is not None:
            try:
                m = self._minhash_texto(texto)
                if m is None:
                    return True
                if self._lsh.query(m):
                    self.duplicados_aprox += 1
                    return False
                # Guarda p/ futuras consultas
                ident = chave
                self._lsh.insert(ident, m)
                self._minhashes[ident] = m
            except Exception:
                pass  # dedup aproximado falhou → segue (não é fatal)
        return True

    def __len__(self) -> int:
        return len(self._vistos_exato)


# ============================================================================
# ETAPA 5 — CLASSIFICAÇÃO SFT vs PRETRAIN (2.6 — NUNCA criar diálogo artificial)
# ============================================================================
def _tem_estrutura_qa(conteudo: dict) -> bool:
    """True se o documento TEM estrutura de QA (roles user/assistant ou
    marcadores Pergunta:/Resposta:). NUNCA inventar diálogo.

    Também reconhece formato de INSTRUÇÃO (Alpaca/Canarim):
    instruction/input/output — é QA estruturado de verdade (prompt → resposta),
    então vira SFT, NÃO texto corrido.
    """
    if not isinstance(conteudo, dict):
        return False
    msgs = conteudo.get("messages") or conteudo.get("conversations") or \
           conteudo.get("conversation") or conteudo.get("chat")
    if isinstance(msgs, list) and msgs:
        # lista de turnos com role — estrutura real de chat
        return True
    # Formato de INSTRUÇÃO (Alpaca/Canarim): instruction(+input) → output
    if conteudo.get("instruction") or conteudo.get("prompt"):
        if conteudo.get("output") or conteudo.get("completion") or \
           conteudo.get("answer"):
            return True
    # Marcadores explícitos Pergunta:/Resposta: no texto
    texto = str(conteudo.get("text") or conteudo.get("content") or "")
    if re.search(r"(?im)^\s*pergunta\s*:", texto) and \
       re.search(r"(?im)^\s*resposta\s*:", texto):
        return True
    return False


def _extrair_messages(conteudo: dict) -> list[dict] | None:
    """Converte estrutura real de QA para ChatML (system/user/assistant).

    Suporta: messages/conversations/chat (lista ou string JSON) E formato de
    INSTRUÇÃO (instruction/input → output) — Alpaca/Canarim.
    """
    msgs = conteudo.get("messages") or conteudo.get("conversations") or \
           conteudo.get("conversation") or conteudo.get("chat")
    if isinstance(msgs, str):
        try:
            msgs = json.loads(msgs)
        except Exception:
            msgs = None

    # Formato de INSTRUÇÃO (Alpaca/Canarim): instruction(+input) → output
    if not isinstance(msgs, list) and \
       (conteudo.get("instruction") or conteudo.get("prompt")):
        instr = str(conteudo.get("instruction") or conteudo.get("prompt") or "").strip()
        entrada = str(conteudo.get("input") or "").strip()
        saida_txt = str(conteudo.get("output") or conteudo.get("completion") or
                        conteudo.get("answer") or "").strip()
        if instr and saida_txt:
            user_txt = f"{instr}\n\n{entrada}".strip() if entrada else instr
            return [
                {"role": "user", "content": user_txt},
                {"role": "assistant", "content": saida_txt},
            ]
        return None

    if not isinstance(msgs, list):
        return None
    saida = []
    for m in msgs:
        if isinstance(m, dict):
            role = str(m.get("role") or m.get("from") or "").lower()
            if role in ("human", "user"):
                role = "user"
            elif role in ("gpt", "assistant", "bot", "model"):
                role = "assistant"
            elif role == "system":
                role = "system"
            else:
                continue
            valor = m.get("content") or m.get("value") or m.get("text")
            if valor:
                saida.append({"role": role, "content": str(valor).strip()})
        elif isinstance(m, str):
            role = "assistant" if len(saida) % 2 == 1 else "user"
            saida.append({"role": role, "content": m.strip()})
    if len(saida) >= 2:
        return saida
    return None


def _classificar_documento(conteudo: dict) -> tuple[Optional[dict], str]:
    """(exemplo, tipo). tipo = 'sft' | 'pretrain' | None(descarta).

    REGRA 2.6: texto corrido (sem estrutura de QA) → campo `text` (pretrain).
    NUNCA forçar par user/assistant com o mesmo conteúdo.

    Ordem CORRETA: primeiro verifica estrutura de QA (messages pode existir
    SEM campo text/content — fix 05/08: documentos com messages eram
    descartados como 'sem_texto' antes de checar o QA).
    """
    # 1) Estrutura de QA real (messages/conversations OU marcadores Pergunta:)
    if _tem_estrutura_qa(conteudo):
        msgs = _extrair_messages(conteudo)
        if msgs:
            return {"messages": msgs}, "sft"
        # tinha marcador mas não converteu → tenta texto puro (não inventa)
        texto = str(conteudo.get("text") or conteudo.get("content") or "").strip()
        if texto:
            return {"text": texto}, "pretrain"
        return None, "sem_texto"

    # 2) Texto corrido → pretrain (NUNCA diálogo artificial)
    texto = str(conteudo.get("text") or conteudo.get("content") or "").strip()
    if not texto:
        return None, "sem_texto"
    return {"text": texto}, "pretrain"


# ============================================================================
# ETAPA 6 — ORQUESTRAÇÃO STREAMING (2.3: idioma→limpeza→qualidade→dedup)
# ============================================================================
def _ler_documentos(origem: str) -> Iterator[dict]:
    """Itera os documentos da origem (pasta/arquivo) em STREAMING.

    Suporta: .jsonl, .json (lista ou NDJSON), .txt (texto puro), .parquet.
    Pasta → varre recursivamente. RAM constante (1 documento por vez).

    Fix 05/08: quando uma pasta tem dataset.jsonl E train.parquet (mesmos
    dados em formatos diferentes — comum em downloads HF), prioriza o .parquet
    (mais eficiente) e NÃO processa o .jsonl redundante (evita processar 2x).
    """
    p = Path(origem)
    arquivos: list[Path] = []
    if p.is_dir():
        parquets = sorted(p.rglob("*.parquet"))
        jsonl_dir = sorted(p.rglob("*.jsonl"))
        if parquets and any(f.name.lower() == "dataset.jsonl" for f in jsonl_dir):
            # dataset.jsonl + parquet = mesmo conteúdo → só o parquet
            arquivos = parquets
        else:
            for ext in ("*.jsonl", "*.json", "*.txt", "*.parquet"):
                arquivos.extend(sorted(p.rglob(ext)))
    elif p.is_file():
        arquivos = [p]

    for arq in arquivos:
        ext = arq.suffix.lower()
        try:
            if ext in (".jsonl", ".json"):
                with open(arq, encoding="utf-8", errors="replace") as f:
                    for linha in f:
                        linha = linha.strip()
                        if not linha:
                            continue
                        if len(linha) > TAMANHO_MAX_LINHA:
                            continue  # linha gigante = corrompida
                        try:
                            obj = json.loads(linha)
                        except Exception:
                            continue
                        if isinstance(obj, dict):
                            yield obj
                        elif isinstance(obj, list):
                            for o in obj:
                                if isinstance(o, dict):
                                    yield o
            elif ext == ".txt":
                try:
                    texto = arq.read_text(encoding="utf-8", errors="replace")
                    yield {"text": texto}
                except Exception:
                    continue
            elif ext == ".parquet":
                try:
                    import pyarrow.parquet as pq
                    with pq.ParquetFile(str(arq)) as pf:
                        for batch in pf.iter_batches():
                            for row in batch.to_pylist():
                                if isinstance(row, dict):
                                    yield row
                except Exception:
                    continue
        except Exception:
            continue  # arquivo com problema não derruba o lote


def _texto_principal(doc: dict) -> str:
    """Extrai o texto PRINCIPAL do documento para filtros (idioma/qualidade/dedup).

    Suporta: text/content (texto corrido), messages (concatena conteúdos),
    instruction/input/output (formato Alpaca/Canarim).
    """
    t = str(doc.get("text") or doc.get("content") or "").strip()
    if t:
        return t
    # Formato de instrução
    instr = str(doc.get("instruction") or doc.get("prompt") or "").strip()
    saida = str(doc.get("output") or doc.get("completion") or
                doc.get("answer") or "").strip()
    if instr or saida:
        return f"{instr}\n\n{saida}".strip()
    # Messages: concatena os conteúdos
    msgs = doc.get("messages") or doc.get("conversations") or \
           doc.get("conversation") or doc.get("chat")
    if isinstance(msgs, str):
        try:
            msgs = json.loads(msgs)
        except Exception:
            msgs = None
    if isinstance(msgs, list):
        partes = []
        for m in msgs:
            if isinstance(m, dict):
                partes.append(str(m.get("content") or m.get("value") or
                                  m.get("text") or ""))
            elif isinstance(m, str):
                partes.append(m)
        return "\n".join(p for p in partes if p).strip()
    return ""


def _limpar_documento(doc: dict) -> dict:
    """Aplica a limpeza (ftfy+bs4+URLs) nos campos de texto do documento."""
    limpo = dict(doc)
    for campo in ("text", "content", "instruction", "prompt",
                  "output", "completion", "answer"):
        if campo in limpo:
            limpo[campo] = _limpar_texto(str(limpo[campo] or ""))
    # Limpa conteúdos das messages (se houver)
    msgs = limpo.get("messages") or limpo.get("conversations") or \
           limpo.get("conversation") or limpo.get("chat")
    if isinstance(msgs, list):
        novas = []
        for m in msgs:
            if isinstance(m, dict) and "content" in m:
                m = dict(m)
                m["content"] = _limpar_texto(str(m.get("content") or ""))
            novas.append(m)
        for chave in ("messages", "conversations", "conversation", "chat"):
            if chave in limpo:
                limpo[chave] = novas
                break
    return limpo


def _processar_documento(doc: dict, filtro_idioma: "_FiltroIdioma",
                         dedup: "_Deduplicador", exigir_ptbr: bool,
                         contadores: dict) -> tuple[Optional[dict], str]:
    """Processa UM documento seguindo a ORDEM 2.3. Retorna (exemplo, tipo)."""
    # 0) Texto bruto (para chave de dedup exato — barato, primeiro)
    texto_bruto = _texto_principal(doc)
    if not texto_bruto.strip():
        contadores["sem_texto"] += 1
        return None, "sem_texto"

    # 1) FILTRO DE IDIOMA PRIMEIRO (2.3) — descarta antes de gastar CPU
    if exigir_ptbr and not filtro_idioma.eh_portugues(texto_bruto):
        contadores["nao_pt"] += 1
        return None, "nao_pt"

    # 1b) FILTRO DE RUÍDO DE IA (05/08) — datasets sintéticos vazam o
    # "pensamento" do modelo gerador ("the user gave instructions...") — lixo.
    # Barato (regex na amostra do texto), roda ANTES da limpeza pesada.
    if _tem_ruido_ia(texto_bruto):
        contadores["ruido_ia"] += 1
        return None, "ruido_ia"

    # 2) LIMPEZA (ftfy + bs4 + URLs) (2.4) — em todos os campos de texto
    doc = _limpar_documento(doc)
    texto_limpo_principal = _texto_principal(doc)

    # 3) FILTRO DE QUALIDADE (2.2)
    ok, motivo = _filtro_qualidade(texto_limpo_principal or texto_bruto)
    if not ok:
        contadores["qualidade"] += 1
        return None, f"qualidade:{motivo}"

    # 4) DEDUP (2.1) — exato + aproximado
    if not dedup.eh_novo(texto_limpo_principal or texto_bruto):
        contadores["duplicado"] += 1
        return None, "duplicado"

    # 5) CLASSIFICAÇÃO (2.6)
    exemplo, tipo = _classificar_documento(doc)
    return exemplo, tipo


# ============================================================================
# ETAPA 7 — SAÍDA PARQUET (via datasets, streaming, arquivos PARCIAIS)
# ============================================================================
# Fix 05/08: escrever sempre no MESMO arquivo sobrescreve os lotes anteriores
# (só o último flush ficava — 996 de 38.996). Agora cada flush grava um
# arquivo parcial (rigel_sft.part000.parquet, .part001...) e o final MESCLA
# tudo. RAM constante (1 lote por vez).


def _salvar_lote_parquet(exemplos: list[dict], caminho_part: str) -> int:
    """Salva UM lote em .parquet (pyarrow com schema EXPLÍCITO).

    Fix 05/08: `datasets.Dataset.from_list` na v5 ACHATA dicts aninhados
    (messages virava 1 linha por mensagem — role/content, perdendo a estrutura
    de exemplo). Agora usamos pyarrow com schema explícito: cada exemplo = 1
    linha com a coluna `messages` (lista de structs) ou `text`.
    """
    if not exemplos:
        return 0
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        if all("messages" in e for e in exemplos):
            # Schema explícito: messages = list<struct<role, content>>
            campo_role = pa.field("role", pa.string())
            campo_content = pa.field("content", pa.string())
            struct_turno = pa.struct([campo_role, campo_content])
            campo_messages = pa.field("messages", pa.list_(struct_turno))
            schema = pa.schema([campo_messages])
            arrays = []
            for e in exemplos:
                turnos = []
                for m in e.get("messages") or []:
                    if isinstance(m, dict):
                        turnos.append({
                            "role": str(m.get("role") or ""),
                            "content": str(m.get("content") or ""),
                        })
                arrays.append(turnos)
            coluna = pa.array(arrays, type=pa.list_(struct_turno))
            tabela = pa.Table.from_arrays([coluna], schema=schema)
        else:
            # Pretrain: coluna `text`
            chaves = sorted(set().union(*(e.keys() for e in exemplos)))
            dados = {k: [e.get(k) for e in exemplos] for k in chaves}
            tabela = pa.table(dados)
        pq.write_table(tabela, caminho_part)
        return len(exemplos)
    except Exception as e:
        print(f"  ⚠️  Não consegui salvar {caminho_part}: {e}")
        jsonl = caminho_part.replace(".parquet", ".jsonl")
        with open(jsonl, "w", encoding="utf-8") as f:
            for e in exemplos:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return len(exemplos)


def _mesclar_parquets(partes: list[str], final: str) -> int:
    """Mescla os arquivos parciais em UM parquet final. Retorna nº de linhas.

    Usa pyarrow (leitura em streaming por batches, sem carregar tudo).
    Se não houver partes, não cria arquivo.
    """
    if not partes:
        return 0
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        tabelas = []
        total = 0
        for p in partes:
            t = pq.read_table(p)
            total += t.num_rows
            tabelas.append(t)
        if not tabelas:
            return 0
        # Concatena (mesmo schema) e escreve
        final_tabela = pa.concat_tables(tabelas)
        pq.write_table(final_tabela, final)
        return total
    except Exception as e:
        print(f"  ⚠️  Mescla falhou ({e}) — mantendo arquivos parciais em "
              f"{os.path.dirname(final)}/")
        return 0


class _EscritorParquet:
    """Grava lotes em arquivos parciais numerados; mescla no fechamento.

    Streaming: RAM constante (1 lote de cada vez no disco).
    """

    def __init__(self, caminho_final: str, lote: int = 5000):
        self.caminho_final = caminho_final
        self.lote = lote
        self._indice = 0
        self._partes: list[str] = []
        self.gravados = 0

    def gravar(self, exemplos: list[dict]) -> int:
        if not exemplos:
            return 0
        part = f"{self.caminho_final}.part{self._indice:03d}.parquet"
        n = _salvar_lote_parquet(exemplos, part)
        if n:
            self._partes.append(part)
            self._indice += 1
            self.gravados += n
        return n

    def fechar(self) -> int:
        """Mescla os parciais no arquivo final e apaga os parciais."""
        if not self._partes:
            return self.gravados
        total = _mesclar_parquets(self._partes, self.caminho_final)
        # Apaga os parciais (só se a mescla funcionou)
        if total:
            for p in self._partes:
                try:
                    os.remove(p)
                except Exception:
                    pass
            self._partes = []
        return self.gravados


# ============================================================================
# MAIN — orquestração + progresso ao vivo (regra de ouro 05/08)
# ============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pipeline LEVE de limpeza de datasets (SFT + Pretrain) para SLMs")
    ap.add_argument("--origem", required=True, help="Pasta ou arquivo de origem")
    ap.add_argument("--saida", default="dados/processed",
                    help="Pasta de saída (default: dados/processed)")
    ap.add_argument("--lid-model", default="",
                    help="Caminho do modelo fasttext lid.176.bin")
    ap.add_argument("--max-docs", type=int, default=0,
                    help="Limita nº de documentos (teste rápido)")
    ap.add_argument("--sem-ptbr", action="store_true",
                    help="Desliga o filtro de idioma PT-BR (não recomendado)")
    ap.add_argument("--lote", type=int, default=5000,
                    help="Exemplos por lote de escrita (RAM controlada)")
    args = ap.parse_args()

    t_inicio = time.time()
    os.makedirs(args.saida, exist_ok=True)
    origem = args.origem
    if not os.path.exists(origem):
        print(f"ERRO: origem não encontrada: {origem}")
        return 1

    print(f"📥 Origem: {origem}")
    print(f"📤 Saída:  {args.saida}")
    print(f"{'⚠️  FILTRO DE IDIOMA DESLIGADO (--sem-ptbr)' if args.sem_ptbr else '🌐 Filtro de idioma: ATIVO'}")

    # Carrega o filtro de idioma (fasttext lid.176) — pode baixar
    filtro_idioma = _FiltroIdioma(args.lid_model)
    if filtro_idioma.aviso:
        print(f"  ℹ️  {filtro_idioma.aviso}")

    dedup = _Deduplicador()
    contadores = {
        "lidos": 0, "sem_texto": 0, "nao_pt": 0, "qualidade": 0,
        "duplicado": 0, "ruido_ia": 0, "sft": 0, "pretrain": 0,
        "arquivos": 0,
    }

    lote_sft: list[dict] = []
    lote_pre: list[dict] = []
    caminho_sft = os.path.join(args.saida, "rigel_sft.parquet")
    caminho_pre = os.path.join(args.saida, "rigel_pretrain.parquet")
    escritor_sft = _EscritorParquet(caminho_sft, lote=args.lote)
    escritor_pre = _EscritorParquet(caminho_pre, lote=args.lote)

    print("\n⏳ Processando em STREAMING (memória constante)...")

    t_loop = time.time()

    def _flush_lotes() -> None:
        if lote_sft:
            escritor_sft.gravar(lote_sft)
            lote_sft.clear()
        if lote_pre:
            escritor_pre.gravar(lote_pre)
            lote_pre.clear()
        contadores["sft"] = escritor_sft.gravados
        contadores["pretrain"] = escritor_pre.gravados
        # Progresso ao vivo (barra no terminal + arquivo p/ o dashboard)
        total = contadores["lidos"]
        pct = min(100.0, (contadores["sft"] + contadores["pretrain"]) /
                  max(1, total) * 100)
        _atualizar_progresso(
            pct=round(pct, 1), lidos=total,
            sft=contadores["sft"], pretrain=contadores["pretrain"],
            descartados=contadores["qualidade"] + contadores["nao_pt"] +
                        contadores["duplicado"] + contadores["sem_texto"] +
                        contadores["ruido_ia"],
            decorrido_s=round(time.time() - t_loop, 1),
            origem=origem, saida=args.saida,
            arquivo_atual=os.path.basename(origem))
        print(f"  ⏳ {pct:5.1f}% | {total} lidos | "
              f"SFT={contadores['sft']} Pretrain={contadores['pretrain']} "
              f"desc={contadores['qualidade']+contadores['nao_pt']+contadores['duplicado']+contadores['ruido_ia']} "
              f"| flush", flush=True)

    for doc in _ler_documentos(origem):
        contadores["lidos"] += 1
        if args.max_docs and contadores["lidos"] > args.max_docs:
            break
        try:
            exemplo, tipo = _processar_documento(
                doc, filtro_idioma, dedup, exigir_ptbr=not args.sem_ptbr,
                contadores=contadores)
        except Exception:
            contadores["qualidade"] += 1  # documento que falhou não derruba
            continue
        if exemplo is None:
            continue
        if tipo == "sft":
            lote_sft.append(exemplo)
        elif tipo == "pretrain":
            lote_pre.append(exemplo)
        # Grava em lotes (RAM controlada)
        if len(lote_sft) + len(lote_pre) >= args.lote:
            _flush_lotes()
        # Progresso leve a cada 500 (sem floodar o terminal) — + arquivo p/ barra
        if contadores["lidos"] % 500 == 0:
            total = contadores["lidos"]
            pct = min(100.0, (contadores["sft"] + contadores["pretrain"]) /
                      max(1, total) * 100)
            _atualizar_progresso(
                pct=round(pct, 1), lidos=total,
                sft=contadores["sft"], pretrain=contadores["pretrain"],
                descartados=contadores["qualidade"] + contadores["nao_pt"] +
                            contadores["duplicado"] + contadores["sem_texto"] +
                            contadores["ruido_ia"],
                decorrido_s=round(time.time() - t_loop, 1),
                origem=origem, saida=args.saida,
                arquivo_atual=os.path.basename(origem))
            print(f"  ⏳ {pct:5.1f}% | {total} lidos | "
                  f"SFT={contadores['sft']} Pretrain={contadores['pretrain']}",
                  flush=True)

    # Flush final + mescla dos parciais no arquivo final
    _flush_lotes()
    escritor_sft.fechar()
    escritor_pre.fechar()
    contadores["sft"] = escritor_sft.gravados
    contadores["pretrain"] = escritor_pre.gravados
    _atualizar_progresso(
        pct=100.0, lidos=contadores["lidos"],
        sft=contadores["sft"], pretrain=contadores["pretrain"],
        descartados=contadores["qualidade"] + contadores["nao_pt"] +
                    contadores["duplicado"] + contadores["sem_texto"] +
                    contadores["ruido_ia"],
        decorrido_s=round(time.time() - t_loop, 1),
        origem=origem, saida=args.saida,
        arquivo_atual="CONCLUÍDO")

    duracao = round(time.time() - t_inicio, 1)
    print(f"\n✅ RESULTADO ({duracao}s):")
    print(f"  Lidos:        {contadores['lidos']}")
    print(f"  SFT:          {contadores['sft']}  → {caminho_sft}")
    print(f"  Pretrain:     {contadores['pretrain']}  → {caminho_pre}")
    print(f"  Não-PT:       {contadores['nao_pt']}")
    print(f"  Qualidade:    {contadores['qualidade']}")
    print(f"  Ruído de IA:  {contadores['ruido_ia']}")
    print(f"  Duplicados:   {contadores['duplicado']} "
          f"(exatos {dedup.duplicados_exatos} + aprox {dedup.duplicados_aprox})")

    # Relatório persistido (regra de ouro: não fica perdido no chat)
    relatorio = {
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "origem": args.origem,
        "saida_dir": args.saida,
        "duracao_s": duracao,
        "contadores": contadores,
        "dedup": {"exatos": dedup.duplicados_exatos,
                  "aproximados": dedup.duplicados_aprox,
                  "limiar_minhash": LIMIAR_MINHASH},
        "filtro_idioma": {"disponivel": filtro_idioma.disponivel,
                          "aviso": filtro_idioma.aviso},
        "limitacao_ptpt": ("fasttext lid.176 não distingue PT-BR de PT-PT; "
                           "heurística opcional de palavras típicas não ativa "
                           "por padrão (ver 2.5 do prompt)"),
    }
    try:
        with open(os.path.join(args.saida, "limpeza_relatorio.json"), "w",
                  encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        print(f"  Relatório:    {os.path.join(args.saida, 'limpeza_relatorio.json')}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
