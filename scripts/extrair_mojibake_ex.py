#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""extrair_mojibake_ex.py — Mostra mensagens REAIS com mojibake de um JSONL.

Uso:
  python scripts/extrair_mojibake_ex.py <arquivo> [n_exemplos]
"""
from __future__ import annotations

import json
import os
import re
import sys

RE = re.compile(r"[\u00c0-\u00ff]|Ã.|Â.")


def main() -> int:
    arquivo = sys.argv[1] if len(sys.argv) > 1 else "dados/processed/jsonl/rigeljsonl_20260802_0136/rigeljsonl_20260802_0136_00001.jsonl"
    n_alvo = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    if not os.path.exists(arquivo):
        print("Arquivo não existe:", arquivo)
        return 1
    achados = 0
    with open(arquivo, encoding="utf-8", errors="replace") as f:
        for num_linha, linha in enumerate(f, 1):
            try:
                obj = json.loads(linha)
            except Exception:
                continue
            msgs = obj.get("messages") or []
            for m in msgs:
                c = m.get("content") or ""
                if RE.search(c):
                    achados += 1
                    print(f"linha {num_linha} | role={m.get('role')}")
                    print(f"  content={c[:300]!r}")
                    if achados >= n_alvo:
                        print("\nTOTAL de mensagens com mojibake encontradas até o limite:", achados)
                        return 0
    print("Nenhum mojibake encontrado (ou arquivo menor que o esperado). Total:", achados)
    return 0


if __name__ == "__main__":
    sys.exit(main())
