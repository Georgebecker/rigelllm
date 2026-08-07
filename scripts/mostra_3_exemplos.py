# -*- coding: utf-8 -*-
"""mostra_3_exemplos.py — Mostra 3 exemplos completos do pretrain limpo."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pyarrow.parquet as pq

caminho = "dados/processed/limpo_madras1_v2/rigel_pretrain.parquet"
pf = pq.ParquetFile(caminho)
tb = pf.read().to_pylist()

for i in range(3):
    print("=" * 70)
    print(f"EXEMPLO {i+1} (de {len(tb)}) — {len(tb[i]['text'])} caracteres")
    print("=" * 70)
    print(tb[i]["text"])
    print()
