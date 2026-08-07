# -*- coding: utf-8 -*-
"""ver_parquet.py — Verifica o conteúdo dos parquets gerados pelo teste."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datasets import load_dataset

for nome in ("rigel_sft", "rigel_pretrain"):
    try:
        ds = load_dataset("parquet",
                          data_files=f"dados/teste_limpeza/saida2/{nome}.parquet",
                          split="train")
        print(f"=== {nome}: {len(ds)} exemplos ===")
        for i, e in enumerate(ds[:2]):
            if "messages" in e:
                partes = [(m.get("role"),
                           str(m.get("content", ""))[:40]) for m in e["messages"]]
                print(f"  [{i}] messages: {partes}")
            else:
                print(f"  [{i}] text: {str(e.get('text', ''))[:80]}")
    except Exception as ex:
        print(f"{nome}: ERRO {type(ex).__name__}: {ex}")
