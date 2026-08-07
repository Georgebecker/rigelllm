# -*- coding: utf-8 -*-
"""ver_canarim_final.py — Verifica o parquet final do Canarim."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pyarrow.parquet as pq

caminho = "dados/processed/limpo_canarim/rigel_sft.parquet"
try:
    pf = pq.ParquetFile(caminho)
    print(f"SFT final: {pf.metadata.num_rows} linhas (exemplos)")
    print("Colunas topo:", pf.schema_arrow.names)
    print("Tipo coluna:", pf.schema_arrow.field("messages").type)
    tb = pf.read().to_pylist()
    print()
    print("=== Amostra (2 exemplos) ===")
    for e in tb[:2]:
        for m in e["messages"]:
            print(f"  [{m['role']}] {m['content'][:90]}")
        print("  ---")
    import os
    print(f"\nTamanho: {os.path.getsize(caminho)/1e6:.1f} MB")
except Exception as e:
    print("ERRO:", type(e).__name__, e)
