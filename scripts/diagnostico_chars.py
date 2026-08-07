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


def main() -> int:
    arquivo = sys.argv[1] if len(sys.argv) > 1 else "dados/processed/jsonl/rigeljsonl_20260802_0136/rigeljsonl_20260802_0136_00001.jsonl"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    contador: Counter = Counter()
    with open(arquivo, encoding="utf-8", errors="replace") as f:
        for linha in f:
            for ch in linha:
                if ch not in ABNT2_ACEITOS and ch not in "\r\n\t ":
                    contador[ch] += 1
    print(f"Caracteres que seriam removidos em {os.path.basename(arquivo)}:")
    print(f"{'char':<8} {'hex':<8} {'nome':<30} {'n':>6}")
    for ch, num in contador.most_common(n):
        try:
            nome = unicodedata_name(ch) if False else ch.encode("unicode_escape").decode()
        except Exception:
            nome = "?"
        print(f"{ch!r:<8} {hex(ord(ch)):<8} {nome:<30} {num:>6}")
    print("\nTOTAL de chars a remover:", sum(contador.values()))
    return 0


if __name__ == "__main__":
    import unicodedata as _u
    main()
