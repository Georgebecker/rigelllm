# -*- coding: utf-8 -*-
"""ver_alpaca_sft.py — Verifica o SFT gerado do alpaca."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pyarrow.parquet as pq

pf = pq.ParquetFile("dados/processed/limpo_alpaca/rigel_sft.parquet")
print("SFT:", pf.metadata.num_rows, "linhas | schema:", [c.name for c in pf.schema])
tb = pf.read().to_pylist()
print()
print("=== Amostra (2 exemplos) ===")
for e in tb[:2]:
    for m in e["messages"]:
        print(f"  [{m['role']}] {m['content'][:100]}")
    print("  ---")
