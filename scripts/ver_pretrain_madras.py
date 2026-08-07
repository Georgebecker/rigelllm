# -*- coding: utf-8 -*-
"""ver_pretrain_madras.py — Verifica o pretrain do Madras1 v2."""
import sys, os
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pyarrow.parquet as pq

caminho = "dados/processed/limpo_madras1_v2/rigel_pretrain.parquet"
pf = pq.ParquetFile(caminho)
print(f"Pretrain: {pf.metadata.num_rows} linhas")
print("Colunas topo:", pf.schema_arrow.names)
print("Tipo coluna:", pf.schema_arrow.field("text").type)
tb = pf.read().to_pylist()
print()
print("=== Amostra (1 exemplo) ===")
print(str(tb[0]["text"])[:300])
print()
print(f"Tamanho: {os.path.getsize(caminho)/1e6:.1f} MB")
