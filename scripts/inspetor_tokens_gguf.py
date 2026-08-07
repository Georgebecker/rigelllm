#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""inspetor_tokens_gguf.py — Inspeciona o array de tokens do GGUF e compara
com o tokenizer.json de origem (para achar onde o decode quebra).

Uso:
  python scripts/inspetor_tokens_gguf.py [gguf] [ids...]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gguf import GGUFReader  # noqa: E402


def ler_tokens_gguf(caminho: str) -> list[str]:
    """Extrai o array de strings tokenizer.ggml.tokens do GGUF."""
    r = GGUFReader(caminho)
    f = r.fields.get("tokenizer.ggml.tokens")
    if f is None:
        return []
    try:
        return list(f.contents())
    except Exception as e:
        print("Erro ao ler contents:", e)
        return []


def main() -> int:
    gguf = sys.argv[1] if len(sys.argv) > 1 else "gguf/rigelslm_Q4_K_M.gguf"
    ids = [int(x) for x in sys.argv[2:]] or [0, 1, 2, 3, 4, 50, 323, 120, 16]
    tokens = ler_tokens_gguf(gguf)
    print(f"GGUF: {gguf} | tokens lidos do array: {len(tokens)}")
    print("\n== tokens no GGUF ==")
    for i in ids:
        print(f"  {i}: {tokens[i]!r}" if i < len(tokens) else f"  {i}: (fora do range)")
    # compara com tokenizer.json
    import json
    tj = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tokenizer", "tokenizer.json")
    if os.path.exists(tj):
        vocab = json.load(open(tj, encoding="utf-8"))["model"]["vocab"]
        inv = {v: k for k, v in vocab.items()}
        print("\n== tokenizer.json (origem) ==")
        for i in ids:
            print(f"  {i}: {inv.get(i, '?')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
