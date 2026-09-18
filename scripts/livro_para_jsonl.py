# -*- coding: utf-8 -*-
"""
livro_para_jsonl.py — Converte um livro TXT limpo (texto corrido) em JSONL SFT.

Uso:
    python scripts/livro_para_jsonl.py --txt dados/gerados/txt_livros/X.txt \
        --saida dados/gerados/jsonl/livros/X.jsonl [--max-chars 6000] [--max-exemplos N]

Por que existe:
    O treinador local (treinar_com_jsonl.py) é SFT puro — só aceita "messages".
    Texto corrido (pré-treino) é descartado silenciosamente. Este script converte
    capítulos de livros em exemplos SFT (tipo "artigo") no schema padrão do Rigel,
    respeitando a regra de ouro: material verificado/estruturado antes do treino.

O que faz:
    1. Lê o TXT limpo (UTF-8) e divide em capítulos (marcador "Capítulo N").
    2. Deriva um TEMA de cada capítulo (título curto após o marcador, senão 1ª frase).
    3. Fatia capítulos longos em chunks (--max-chars, overlap 200) para caber no seq_len.
    4. Gera exemplos SFT: user = instrução de artigo variada + tema; assistant = chunk.
    5. Escreve JSONL no schema padrão (messages + _id/_fonte/_tipo/_categoria/_assunto/_idioma/_data).
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Marcador de capítulo: "Capítulo I", "Capítulo 1", "CAPÍTULO II"...
_RE_CAPITULO = re.compile(r"(?im)^\s*(cap[íi]tulo\s+[ivxlcdm]+|\d{1,3}\s*[°º]?\s*parte|parte\s+[ivxlcdm]+)\s*$")

# Lixo de metadados de impressão/edição que sobra nos PDFs
_RE_LIXO = re.compile(r"(?i)(sol\.indd|bb\s+preto|^\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$|^\s*www\.|^\s*http)")
# Linha solta que é só número de página (1-4 dígitos)
_RE_NUM_PAGINA = re.compile(r"^\d{1,4}\s*$")
# Linha que é só número de página romano (i, v, x...) — evita "29" real
_RE_NUM_ROMANO = re.compile(r"^[ivxlcdm]{1,4}\s*$", re.IGNORECASE)

# Instruções variadas de artigo: modelo generaliza quando vê DIFERENTES pedidos
_INSTRUCOES_ARTIGO = (
    "Escreva um texto bem estruturado sobre: {tema}.",
    "Produza um artigo detalhado sobre: {tema}.",
    "Desenvolva um texto com introdução e desenvolvimento sobre: {tema}.",
    "Redija um texto informativo a respeito de: {tema}.",
    "Escreva sobre o seguinte assunto, de forma clara e organizada: {tema}.",
)


def _id(texto: str) -> str:
    return hashlib.md5(texto.encode("utf-8")).hexdigest()[:16]


# header de página com letterspacing do PDF (ex.: "h i stó r i a ... | j osé ...")
_RE_HEADER = re.compile(r"\|[a-zçáéíóúâêôãõ]")
# header colado NO MEIO do texto: run de letras espaçadas (3+) + "|" + letras espaçadas.
# A barra "|" é âncora forte: quase nunca aparece em PT-BR normal.
_RE_HEADER_MEIO = re.compile(
    r"[a-zà-úç](?:[ ]+[a-zà-úç]){2,}[^|]*\|[a-zà-úç](?:[ ]+[a-zà-úç])+",
    re.IGNORECASE,
)
# data/hora de impressão embutida no texto ("02/10/14 17:10")
_RE_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}\b")


def _limpar_chunk(texto: str) -> str:
    linhas = []
    for linha in texto.splitlines():
        s = linha.strip()
        if not s:
            continue
        if _RE_LIXO.search(s):
            continue
        if _RE_NUM_PAGINA.match(s) or _RE_NUM_ROMANO.match(s):
            continue
        # header de página (letterspacing com barra "|")
        if _RE_HEADER.search(s) and s.count(" ") > len(s) / 3:
            continue
        # header colado no meio do texto (letras espaçadas + "|")
        s = _RE_HEADER_MEIO.sub(" ", s).strip()
        # remove data/hora de impressão no meio da linha
        s = _RE_DATA.sub("", s).strip()
        if not s:
            continue
        linhas.append(s)
    return " ".join(linhas).strip()


def _parece_sumario(corpo: str) -> bool:
    """Sumário/índice: bloco com muitos números de página soltos e pouco texto real.

    Detecta 3 padrões (correção 17/08 — o sumário de 'a-filha-do-barao' escapava):
      1. Palavra 'SUMÁRIO'/'ÍNDICE' em destaque no bloco.
      2. Linhas com pontos de liderança + número de página na MESMA linha
         (ex.: 'PERSEGUIÇÃO - PRIMEIRA PARTE ...............06').
      3. Linhas que são só número de página + pouco texto real (< 300 chars).
    """
    linhas = [l.strip() for l in corpo.splitlines() if l.strip()]
    if not linhas:
        return True

    # 1) palavra-chave de sumário/índice em destaque (início de linha)
    tem_cabecalho = any(re.match(r"(?i)^\s*(s[uú]m[aá]rio|índice|index)\b", l) for l in linhas)

    # 2) linhas com pontos de liderança + número (padrão clássico de sumário)
    lideranca = sum(1 for l in linhas if _RE_LINHA_LIDERANCA.match(l))

    # 3) linhas que são só número de página
    nums = sum(1 for l in linhas if _RE_NUM_PAGINA.match(l) or _RE_NUM_ROMANO.match(l))
    texto_real = " ".join(
        l for l in linhas
        if not (_RE_NUM_PAGINA.match(l) or _RE_NUM_ROMANO.match(l) or _RE_LINHA_LIDERANCA.match(l)))
    if len(texto_real.strip()) < 300:
        return True
    if nums / len(linhas) > 0.35:
        return True
    # muitas linhas de liderança (pelo menos 3) = sumário
    if lideranca >= 3 and (lideranca + nums) / len(linhas) > 0.4:
        return True
    if tem_cabecalho and (lideranca + nums) >= 3:
        return True
    return False


# Cabeçalho de sumário/índice (linha individual — sem \n, pois splitlines remove)
_RE_SUMARIO_INICIO = re.compile(
    r"(?i)^\s*(s[uú]m[aá]rio|índice|index)\b"
)
# Linha de sumário: 'TÍTULO ....... 04' OU 'TÍTULO . . . . . . 04' (pontos com
# espaços — formato real dos PDFs extraídos pelo pdfplumber). Requer 3+ pontos
# e termina com número de página (1-4 dígitos).
_RE_LINHA_LIDERANCA = re.compile(r"^.{3,70}(?:\.\s*){3,}\s*\d{1,4}\s*$")


def _remover_sumario(texto: str) -> str:
    """Remove o bloco de SUMÁRIO/ÍNDICE do início do texto (correção 17/08).

    Livros sem marcador 'Capítulo N' viram um bloco único — o sumário do
    início ficava dentro dele. Detecta:
      1. Cabeçalho 'SUMÁRIO'/'ÍNDICE' seguido de linhas com pontos + número
         (ex.: 'PERSEGUIÇÃO - PRIMEIRA PARTE ...............06').
      2. Linhas soltas com pontos de liderança + número de página (remove).
    Devolve o texto sem o sumário. Nunca falha.
    """
    if not texto or len(texto) < 50:
        return texto
    try:
        linhas = texto.splitlines()
        # acha linha do cabeçalho SUMÁRIO/ÍNDICE
        inicio = None
        for i, l in enumerate(linhas):
            if _RE_SUMARIO_INICIO.match(l):
                inicio = i
                break
        if inicio is not None:
            # consome as linhas seguintes que parecem sumário (liderança ou curtas)
            j = inicio + 1
            consumidas = 0
            while j < len(linhas):
                l = linhas[j].strip()
                if not l:
                    j += 1
                    continue
                if _RE_LINHA_LIDERANCA.match(l) or len(l) <= 40 and l[-1:].isdigit():
                    consumidas += 1
                    j += 1
                elif len(l) <= 45 and not l.endswith((".", ":", ";", ",")) \
                        and not _RE_LINHA_LIDERANCA.match(l):
                    # título curto de sumário (sem pontos) — consome se vier após
                    # pelo menos 2 linhas de liderança já consumidas
                    if consumidas >= 2:
                        consumidas += 1
                        j += 1
                    else:
                        break
                else:
                    break
            # só remove se consumiu um trecho significativo (>= 3 linhas)
            if consumidas >= 3:
                texto = "\n".join(linhas[j:]).strip()

        # remove linhas soltas de liderança que sobrarem no meio
        linhas = texto.splitlines()
        texto = "\n".join(l for l in linhas if not _RE_LINHA_LIDERANCA.match(l.strip()))
        return texto.strip()
    except Exception:
        return texto


def _tema_do_capitulo(corpo: str, titulo: str | None) -> str:
    """Título real do capítulo (linha curta após o marcador), senão 1ª frase."""
    if titulo and 3 <= len(titulo) <= 90 and not _RE_LIXO.search(titulo) \
            and not _RE_NUM_PAGINA.match(titulo) and not _RE_HEADER.search(titulo):
        return titulo
    # primeira frase com 20-90 chars
    frases = re.split(r"(?<=[.!?])\s+", corpo)
    for f in frases:
        f = f.strip()
        if 20 <= len(f) <= 90:
            return f
    return corpo[:80].strip()


def _fatiar(texto: str, max_chars: int, overlap: int = 200) -> list[str]:
    if len(texto) <= max_chars:
        return [texto]
    partes = []
    i = 0
    while i < len(texto):
        fim = min(i + max_chars, len(texto))
        # tenta cortar em fim de frase próximo
        if fim < len(texto):
            corte = texto.rfind(". ", i + max_chars // 2, fim)
            if corte > 0:
                fim = corte + 1
        partes.append(texto[i:fim].strip())
        if fim >= len(texto):
            break
        i = max(fim - overlap, i + max_chars // 2)
    return [p for p in partes if len(p) > 100]


def _tema_do_chunk(chunk: str) -> str:
    """Tema ÚNICO por chunk (primeira frase) — evita duplicatas de pergunta
    no treino (o dedup do treinador é por hash da pergunta)."""
    frases = re.split(r"(?<=[.!?])\s+", chunk)
    for f in frases:
        f = f.strip()
        if 20 <= len(f) <= 90:
            return f
    return chunk[:80].strip()


def converter(txt_path: Path, saida_path: Path, max_chars: int, max_exemplos: int | None) -> dict:
    texto = txt_path.read_text(encoding="utf-8")
    # 🔧 remove sumário/índice do início (correção 17/08 — não é material de treino)
    texto = _remover_sumario(texto)
    # pré-divisão em capítulos
    posicoes = [m.start() for m in _RE_CAPITULO.finditer(texto)]
    if not posicoes:
        # sem marcador de capítulo: trata o livro todo como um bloco
        blocos = [("", texto)]
    else:
        blocos = []
        for i, inicio in enumerate(posicoes):
            fim = posicoes[i + 1] if i + 1 < len(posicoes) else len(texto)
            cab = texto[inicio:fim]
            # separa linha do marcador do restante
            m = _RE_CAPITULO.search(cab)
            resto = cab[m.end():] if m else cab
            linhas = resto.splitlines()
            corpo = "\n".join(l for l in linhas if l.strip())
            blocos.append((m.group(1).strip() if m else "", corpo))

    fonte = txt_path.stem
    exemplos = 0
    descartados = 0
    sumario = 0
    with saida_path.open("w", encoding="utf-8") as f:
        for titulo, corpo in blocos:
            # pula sumário/índice (marcadores + números de página)
            if _parece_sumario(corpo):
                sumario += 1
                continue
            # título real do capítulo = 1ª linha curta e não-lixo após o marcador
            titulo_real = None
            for l in corpo.splitlines():
                s = l.strip()
                if not s or _RE_LIXO.search(s) or _RE_NUM_PAGINA.match(s) \
                        or _RE_NUM_ROMANO.match(s) or _RE_HEADER.search(s):
                    continue
                if 3 <= len(s) <= 90:
                    titulo_real = s
                    break
            corpo_limpo = _limpar_chunk(corpo)
            if len(corpo_limpo) < 100:
                descartados += 1
                continue
            tema_capitulo = _tema_do_capitulo(corpo_limpo, titulo_real or titulo)
            for chunk in _fatiar(corpo_limpo, max_chars):
                idx = int(hashlib.md5(chunk.encode("utf-8")).hexdigest()[:8], 16) % len(_INSTRUCOES_ARTIGO)
                # tema ÚNICO por chunk (primeira frase) — evita duplicatas no dedup do treinador
                tema = _tema_do_chunk(chunk) or tema_capitulo
                pergunta = _INSTRUCOES_ARTIGO[idx].format(tema=tema)
                exemplo = {
                    "messages": [
                        {"role": "system", "content": "Você é o Rigel, um assistente em português brasileiro."},
                        {"role": "user", "content": pergunta},
                        {"role": "assistant", "content": chunk},
                    ],
                    "_id": _id(pergunta + "|" + chunk),
                    "_fonte": fonte,
                    "_tipo": "artigo",
                    "_categoria": "livros",
                    "_assunto": tema[:80],
                    "_idioma": "pt-BR",
                    "_data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                f.write(json.dumps(exemplo, ensure_ascii=False) + "\n")
                exemplos += 1
                if max_exemplos and exemplos >= max_exemplos:
                    return {"exemplos": exemplos, "descartados": descartados, "capitulos": len(blocos), "sumario": sumario, "cortado": True}
    return {"exemplos": exemplos, "descartados": descartados, "capitulos": len(blocos), "sumario": sumario, "cortado": False}


def main() -> int:
    ap = argparse.ArgumentParser(description="Livro TXT → JSONL SFT (artigo).")
    ap.add_argument("--txt", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--max-chars", type=int, default=6000, help="Tamanho máx. por exemplo (chars).")
    ap.add_argument("--max-exemplos", type=int, default=None)
    args = ap.parse_args()

    txt = Path(args.txt)
    if not txt.exists():
        print(f"ERRO: {txt} não encontrado", file=sys.stderr)
        return 1
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    r = converter(txt, saida, args.max_chars, args.max_exemplos)
    print(f"OK: {r['exemplos']} exemplos | {r['capitulos']} capítulos | sumário {r['sumario']} | descartados {r['descartados']} | cortado={r['cortado']}")
    print(f"Saída: {saida} ({round(saida.stat().st_size/1024,1)} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
