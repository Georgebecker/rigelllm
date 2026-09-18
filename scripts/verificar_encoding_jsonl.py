#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verificar_encoding_jsonl.py — Analisa a codificação dos JSONL de treino.

Detecta: UTF-8 inválido (bytes), caractere U+FFFD (replacement), padrões de
mojibake (latin1/cp1252 lido como UTF-8) e mostra exemplos.

Uso:
  python scripts/verificar_encoding_jsonl.py <pasta> [max_arquivos] [linhas_por_arquivo]
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

# Padrões REAIS de mojibake (UTF-8 bytes interpretados como latin-1/cp1252).
# ⚠️ NÃO usar "Ã"/"Â" isolados: são letras NORMAIS do português ("não", "câmera").
# Mojibake = Ã (C3) ou Â (C2) SEGUIDO de byte latin-1 (80-BF), ex.: Ã©=é, Ã£=ã.
PADROES_MOJIBAKE = [
    (r"\u00c3[\u0080-\u00bf]", "mojibake C3+latino (Ã©=é, Ã£=ã)"),
    (r"\u00c2[\u0080-\u00bf]", "mojibake C2+latino (Â©=©)"),
    (r"\u00e2\u20ac", "cp1252 (â€ = aspas)"),
    (r"\ufffd", "U+FFFD (replacement)"),
]

RE_INVALIDO = re.compile(r"[\ufffd]")
RE_MOJIBAKE = re.compile("|".join(p[0] for p in PADROES_MOJIBAKE))


def _checar_texto(texto: str, bruto: bytes, nome: str) -> dict:
    """Checagens comuns sobre o TEXTO decodificado (encoding/mojibake)."""
    try:
        bruto.decode("utf-8", errors="strict")
        utf8_valido = True
    except UnicodeDecodeError as e:
        utf8_valido = False
        pos_erro = e.start
    qtd_fffd = len(RE_INVALIDO.findall(texto))
    mojis = RE_MOJIBAKE.findall(texto)
    contagem_moji = Counter()
    for m in mojis:
        for padrao, nome_p in PADROES_MOJIBAKE:
            if re.match(padrao, m):
                contagem_moji[nome_p] += 1
                break
    exemplos = []
    for linha in texto.splitlines()[:400]:
        if RE_INVALIDO.search(linha) or RE_MOJIBAKE.search(linha):
            trecho = linha[:160]
            if trecho not in exemplos:
                exemplos.append(trecho)
            if len(exemplos) >= 3:
                break
    return {
        "arquivo": os.path.basename(nome),
        "tamanho_kb": round(len(bruto) / 1024, 1),
        "utf8_valido": utf8_valido,
        "pos_erro": pos_erro if not utf8_valido else None,
        "qtd_fffd": qtd_fffd,
        "total_moji": sum(contagem_moji.values()),
        "tipos_moji": dict(contagem_moji.most_common(5)),
        "exemplos": exemplos,
    }


def _extrair_texto_parquet(caminho: str) -> tuple[str, bytes]:
    """Extrai o texto das colunas string de um .parquet (p/ checar encoding)."""
    try:
        import pyarrow.parquet as pq
        partes = []
        with pq.ParquetFile(caminho) as pf:
            for batch in pf.iter_batches(batch_size=512):
                for row in batch.to_pylist():
                    for v in row.values():
                        if isinstance(v, str):
                            partes.append(v)
                        elif isinstance(v, list):
                            for m in v:
                                if isinstance(m, dict):
                                    for v2 in m.values():
                                        if isinstance(v2, str):
                                            partes.append(v2)
        texto = "\n".join(partes)
        return texto, texto.encode("utf-8", errors="replace")
    except Exception as e:
        return "", ("erro: %s" % e).encode("utf-8")


def analisar_arquivo(caminho: str) -> dict:
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".parquet":
        texto, bruto = _extrair_texto_parquet(caminho)
        if not texto.strip():
            return {"arquivo": os.path.basename(caminho), "tamanho_kb": 0,
                    "utf8_valido": None, "pos_erro": None, "qtd_fffd": 0,
                    "total_moji": 0, "tipos_moji": {}, "exemplos": []}
        return _checar_texto(texto, bruto, caminho)
    with open(caminho, "rb") as f:
        bruto = f.read()
    texto = bruto.decode("utf-8", errors="replace")
    return _checar_texto(texto, bruto, caminho)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    alvo = sys.argv[1] if len(sys.argv) > 1 else "dados/processed/jsonl/rigeljsonl_20260802_0136"
    max_arq = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    raiz = os.path.abspath(alvo)

    # Aceita ARQUIVO (txt/json/jsonl/parquet) OU PASTA
    EXTS = (".txt", ".json", ".jsonl", ".parquet")
    if os.path.isfile(raiz) and raiz.lower().endswith(EXTS):
        caminhos = [raiz]
        print(f"Arquivo: {raiz} | verificando...\n")
    elif os.path.isdir(raiz):
        arquivos = sorted(f for f in os.listdir(raiz)
                          if f.lower().endswith(EXTS))
        caminhos = [os.path.join(raiz, f) for f in arquivos[:max_arq]]
        print(f"Pasta: {raiz} | {len(arquivos)} arquivos | amostrando {len(caminhos)}\n")
    else:
        print("Caminho não encontrado (nem arquivo txt/json/jsonl/parquet nem pasta):", raiz)
        return 1

    if not caminhos:
        print("Nenhum arquivo txt/json/jsonl/parquet encontrado no caminho:", raiz)
        return 1

    total_fffd = 0
    total_moji = 0
    total_nao_utf8 = 0
    for caminho_arq in caminhos:
        r = analisar_arquivo(caminho_arq)
        total_fffd += r["qtd_fffd"]
        total_moji += r["total_moji"]
        if not r["utf8_valido"]:
            total_nao_utf8 += 1
        flag = "❌" if (r["qtd_fffd"] or r["total_moji"] or not r["utf8_valido"]) else "✅"
        print(f"{flag} {r['arquivo']} | {r['tamanho_kb']} KB | UTF8 ok: {r['utf8_valido']}"
              f" | U+FFFD: {r['qtd_fffd']} | mojibake: {r['total_moji']} | tipos: {r['tipos_moji']}")
        for ex in r["exemplos"]:
            print(f"      ex: {ex!r}")
    print("\n=== RESUMO ===")
    print(f"Arquivos com UTF-8 inválido: {total_nao_utf8}/{len(caminhos)}")
    print(f"Total U+FFFD na amostra: {total_fffd}")
    print(f"Total padrões mojibake na amostra: {total_moji}")
    if total_fffd or total_moji or total_nao_utf8:
        print("=> PROBLEMA DE ENCODING CONFIRMADO nos arquivos.")
    else:
        print("=> Amostra limpa (sem mojibake).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
