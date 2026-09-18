#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""diagnostico_chars.py — Mostra os caracteres mais removidos pelo sanitizador
(num arquivo), para calibrar o conjunto ABNT2 sem falso positivo.

Uso:
  python scripts/diagnostico_chars.py <arquivo.jsonl> [n]
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sanitizador_ptbr import ABNT2_ACEITOS  # noqa: E402

EXTS = (".txt", ".json", ".jsonl", ".parquet")


def _valores_string(obj):
    """Itera os valores STRING de um objeto (dict/list) — ignora a sintaxe."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _valores_string(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _valores_string(v)
    elif isinstance(obj, str):
        yield obj


def _extrair_texto(arquivo: str) -> str:
    """Extrai o TEXTO de um arquivo (txt/json/jsonl/parquet) p/ o diagnóstico.
    Para json/jsonl: conta só os VALORES de string (não a sintaxe JSON).
    Para parquet: conta as colunas string."""
    ext = os.path.splitext(arquivo)[1].lower()
    if ext == ".parquet":
        import pyarrow.parquet as pq
        partes = []
        with pq.ParquetFile(arquivo) as pf:
            for batch in pf.iter_batches(batch_size=512):
                for row in batch.to_pylist():
                    for v in row.values():
                        if isinstance(v, str):
                            partes.append(v)
                        elif isinstance(v, list):
                            for m in v:
                                if isinstance(m, dict):
                                    partes.extend(str(x) for x in m.values()
                                                  if isinstance(x, str))
        return "\n".join(partes)
    if ext in (".json", ".jsonl"):
        import json
        partes = []
        with open(arquivo, encoding="utf-8", errors="replace") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    obj = json.loads(linha)
                except Exception:
                    partes.append(linha)
                    continue
                for v in _valores_string(obj):
                    partes.append(v)
        return "\n".join(partes)
    with open(arquivo, encoding="utf-8", errors="replace") as f:
        return f.read()


def _arquivos_alvo(alvo: str) -> list[str]:
    """Arquivo único ou pasta (varre txt/json/jsonl/parquet)."""
    if os.path.isfile(alvo):
        return [alvo] if alvo.lower().endswith(EXTS) else []
    if os.path.isdir(alvo):
        return sorted(os.path.join(alvo, f) for f in os.listdir(alvo)
                      if f.lower().endswith(EXTS))
    return []


def main() -> int:
    alvo = sys.argv[1] if len(sys.argv) > 1 else "dados/processed/jsonl/rigeljsonl_20260802_0136/rigeljsonl_20260802_0136_00001.jsonl"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    arquivos = _arquivos_alvo(alvo)
    if not arquivos:
        print(f"Nenhum arquivo txt/json/jsonl/parquet em: {alvo}")
        return 1
    total_geral = 0
    for arquivo in arquivos:
        contador: Counter = Counter()
        texto = _extrair_texto(arquivo)
        for ch in texto:
            if ch not in ABNT2_ACEITOS and ch not in "\r\n\t ":
                contador[ch] += 1
        total_geral += sum(contador.values())
        print(f"Caracteres que seriam removidos em {os.path.basename(arquivo)}:")
        print(f"{'char':<8} {'hex':<8} {'nome':<30} {'n':>6}")
        for ch, num in contador.most_common(n):
            try:
                nome = ch.encode("unicode_escape").decode()
            except Exception:
                nome = "?"
            print(f"{ch!r:<8} {hex(ord(ch)):<8} {nome:<30} {num:>6}")
        print("  TOTAL de chars a remover:", sum(contador.values()), "\n")
    print("TOTAL GERAL de chars a remover:", total_geral)
    return 0


if __name__ == "__main__":
    main()
