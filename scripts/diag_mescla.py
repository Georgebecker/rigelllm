# -*- coding: utf-8 -*-
"""diag_mescla.py — Inspeciona os arquivos parciais e o final."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
import pyarrow.parquet as pq

pasta = Path("dados/processed/limpo_alpaca")
print("=== Arquivos na pasta ===")
for f in sorted(pasta.glob("*.parquet*")):
    print(f"  {f.name}: {f.stat().st_size/1e6:.2f} MB")

print()
print("=== Schemas ===")
for f in sorted(pasta.glob("*.parquet")):
    try:
        pf = pq.ParquetFile(str(f))
        print(f"  {f.name}: {pf.metadata.num_rows} linhas | {[c.name for c in pf.schema]}")
    except Exception as e:
        print(f"  {f.name}: ERRO {e}")
