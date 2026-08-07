# -*- coding: utf-8 -*-
"""mostra_exemplo_pretrain.py — Mostra 1 exemplo completo do pretrain limpo."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pyarrow.parquet as pq

caminho = "dados/processed/limpo_madras1_v2/rigel_pretrain.parquet"
pf = pq.ParquetFile(caminho)
tb = pf.read().to_pylist()

print("=" * 70)
print("ARQUIVO: dados/processed/limpo_madras1_v2/rigel_pretrain.parquet")
print(f"EXEMPLO 1 de {len(tb)} linhas")
print("=" * 70)
print()
print(tb[0]["text"])
print()
print("=" * 70)
print("EXEMPLO 2")
print("=" * 70)
print()
print(tb[1]["text"])
