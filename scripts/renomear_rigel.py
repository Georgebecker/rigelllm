#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
renomear_rigel.py — REGRA DE OURO: renomeia os JSONL explodidos para o padrão
`Rigel_AAAAMMDD_HHMM.jsonl` (com sufixo de sequência p/ não colidir) e move
para `dados/processed/jsonl`.

Uso:
  python scripts/renomear_rigel.py                                     # processa todas as pastas de dados/gerados/jsonl
  python scripts/renomear_rigel.py dados/gerados/jsonl/Madras1_corpus-ptbr-v2   # só uma pasta
  python scripts/renomear_rigel.py --pasta Madras1_corpus-ptbr-v2      # só uma pasta (nome)
"""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import sys

PROJETO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJETO_ROOT not in sys.path:
    sys.path.insert(0, PROJETO_ROOT)

BASE = os.path.join(PROJETO_ROOT, "dados", "gerados", "jsonl")
DEST = os.path.join(PROJETO_ROOT, "dados", "processed", "jsonl")


def main() -> int:
    ap = argparse.ArgumentParser(description="Renomeia JSONL explodidos p/ Rigel_AAAAMMDD_HHMM.jsonl e move p/ processed/jsonl.")
    ap.add_argument("origem", nargs="?", default=None, help="Caminho da pasta explodida (opcional)")
    ap.add_argument("--pasta", default="", help="Nome da pasta em dados/gerados/jsonl (opcional)")
    args = ap.parse_args()

    os.makedirs(DEST, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    # REGRA DE OURO (organização/proficiência): cada batch vai para SUA própria pasta
    dest_pasta = os.path.join(DEST, f"rigeljsonl_{stamp}")
    os.makedirs(dest_pasta, exist_ok=True)

    pastas = []
    if args.origem:
        p = args.origem if os.path.isabs(args.origem) else os.path.join(PROJETO_ROOT, args.origem)
        pastas.append(p)
    elif args.pasta:
        pastas.append(os.path.join(BASE, args.pasta))
    else:
        if os.path.isdir(BASE):
            pastas = [os.path.join(BASE, d) for d in sorted(os.listdir(BASE))
                      if os.path.isdir(os.path.join(BASE, d))]

    if not pastas:
        print("Nenhuma pasta explodida encontrada em:", BASE)
        return 1

    total = 0
    detalhes = []
    for pasta in pastas:
        if not os.path.isdir(pasta):
            print("Pasta não existe:", pasta)
            continue
        arquivos = sorted(f for f in os.listdir(pasta) if f.endswith(".jsonl"))
        seq = 0
        exemplo = ""
        for f in arquivos:
            seq += 1
            novo = f"Rigel_{stamp}_{seq:03d}.jsonl"
            destino = os.path.join(dest_pasta, novo)
            seq2 = seq
            while os.path.exists(destino):
                seq2 += 1
                novo = f"Rigel_{stamp}_{seq2:03d}.jsonl"
                destino = os.path.join(dest_pasta, novo)
            shutil.move(os.path.join(pasta, f), destino)
            exemplo = novo
            total += 1
        detalhes.append(f"{os.path.basename(pasta)}: {len(arquivos)} arquivos")
        if exemplo:
            print(f"{os.path.basename(pasta)}: {len(arquivos)} arquivos → {dest_pasta} (ex.: {exemplo})")

    print(f"\nTOTAL: {total} arquivos renomeados/movidos → {dest_pasta}")
    print("Prontos para envio ao Google Drive / treino (padrão Rigel_AAAAMMDD_HHMM, pasta do batch).")

    # ⚖️ Valida as regras de ouro APÓS a operação (lição 04/08: verificar sempre)
    try:
        import regras_ouro as ro
        v = ro.verificar_organizacao()
        if v:
            print("⚠️ AINDA há violações de regra de ouro:")
            for x in v:
                print("   •", x)
        else:
            print("✅ Regras de ouro de organização: OK (nenhuma violação).")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
