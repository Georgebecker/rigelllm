#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
atualizar_registro_pastas.py — Migra caminhos de registro de pastas de treino
quando o acervo é reorganizado (padrão por tipo, 18/08/2026).

Uso:
  python scripts/atualizar_registro_pastas.py --registro registro_pastas_treino.json
      --antigo "dados/processed" --novo "dados/processed/parquet"
  (atualiza todo caminho que começa com ANTIGO e aponta para um diretório que
   agora vive em NOVO — com verificação de existência.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _norm(p: str) -> str:
    return os.path.normpath(p).replace("\\", "/")


def main() -> int:
    ap = argparse.ArgumentParser(description="Atualiza caminhos do registro de pastas.")
    ap.add_argument("--registro", required=True, help="arquivo JSON do registro")
    ap.add_argument("--antigo", required=True, help="prefixo de caminho antigo")
    ap.add_argument("--novo", required=True, help="novo prefixo (onde a pasta vive agora)")
    args = ap.parse_args()

    if not os.path.isfile(args.registro):
        print(f"ERRO: registro não encontrado: {args.registro}")
        return 1

    antigo = _norm(args.antigo)
    novo = _norm(args.novo)
    reg = json.loads(Path(args.registro).read_text(encoding="utf-8"))

    atualizados = 0
    para_remover: list[str] = []
    pastas = reg.get("pastas", {})
    for nome, info in list(pastas.items()):
        caminho = _norm(str(info.get("caminho", "")))
        if caminho.startswith(antigo + "/"):
            # novo destino candidato: troca o prefixo e verifica se existe
            novo_caminho = novo + caminho[len(antigo):]
            if os.path.isdir(novo_caminho):
                info["caminho"] = novo_caminho
                atualizados += 1
            elif not os.path.isdir(caminho):
                para_remover.append(nome)  # sumiu dos dois lugares
    for nome in para_remover:
        pastas.pop(nome, None)

    Path(args.registro).write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Registro atualizado: {atualizados} caminho(s) migrados "
          f"{antigo} -> {novo}; {len(para_remover)} entrada(s) removida(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
