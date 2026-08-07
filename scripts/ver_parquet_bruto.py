# -*- coding: utf-8 -*-
"""ver_parquet_bruto.py — Inspeciona o schema e conteúdo bruto dos parquets."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pyarrow.parquet as pq

for nome in ("rigel_sft", "rigel_pretrain"):
    caminho = f"dados/teste_limpeza/saida2/{nome}.parquet"
    print(f"=== {nome} ===")
    pf = pq.ParquetFile(caminho)
    print("  schema:", pf.schema)
    tabela = pf.read()
    for col in tabela.column_names:
        print(f"  coluna {col}: tipo={tabela.schema.field(col).type}")
    for i in range(min(2, tabela.num_rows)):
        print(f"  linha {i}: {tabela.to_pylist()[i]}")
    print()
