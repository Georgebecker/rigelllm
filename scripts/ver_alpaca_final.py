# -*- coding: utf-8 -*-
"""ver_alpaca_final.py — Verifica o parquet final do alpaca (schema + amostra)."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pyarrow.parquet as pq

caminho = "dados/processed/limpo_alpaca/rigel_sft.parquet"
pf = pq.ParquetFile(caminho)
print(f"SFT final: {pf.metadata.num_rows} linhas")
print("Schema:", [c.name for c in pf.schema])
tb = pf.read().to_pylist()
print()
print("=== Amostra (2 exemplos do alpaca) ===")
for e in tb[:2]:
    for m in e["messages"]:
        print(f"  [{m['role']}] {m['content'][:90]}")
    print("  ---")
