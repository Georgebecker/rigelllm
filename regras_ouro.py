#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
regras_ouro.py — Verificador AUTOMÁTICO das regras de ouro de ORGANIZAÇÃO de dados.

Lição 04/08: o usuário teve que apontar arquivos jsonl soltos na raiz de
dados/processed/jsonl. Regra de ouro SEM verificação automática é só intenção.
Por isso este módulo existe: qualquer operação de dados roda isto e reporta
violações.

Regras verificadas:
  1. dados/processed/jsonl e dados/gerados/jsonl: NENHUM .jsonl solto na raiz
     (cada batch deve estar em sua própria pasta rigeljsonl_AAAAMMDD_HHMM/).
  2. Máximo de arquivos por pasta (MAX_FILES_POR_PASTA = 5000).
  3. Nenhuma pasta vazia (lixo sem uso).
"""
from __future__ import annotations

import os
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent
MAX_FILES_POR_PASTA = 5000

_PASTAS = [
    PROJETO_ROOT / "dados" / "processed" / "jsonl",
    PROJETO_ROOT / "dados" / "gerados" / "jsonl",
]


def verificar_organizacao() -> list:
    """Verifica as regras de ouro de organização. Retorna lista de violações (vazia = OK)."""
    violacoes = []
    for base in _PASTAS:
        if not base.is_dir():
            continue
        nome_base = str(base.relative_to(PROJETO_ROOT))
        # 1) arquivos soltos na raiz
        try:
            soltos = [f for f in os.listdir(base)
                      if os.path.isfile(base / f) and f.endswith(".jsonl")]
        except Exception:
            soltos = []
        if soltos:
            violacoes.append(
                f"{nome_base}: {len(soltos)} arquivo(s) jsonl SOLTO(S) na raiz "
                "(devem estar em pasta própria do batch)")
        # 2) > MAX_FILES_POR_PASTA  e  3) pastas vazias
        try:
            itens = sorted(os.listdir(base))
        except Exception:
            itens = []
        for item in itens:
            p = base / item
            if not p.is_dir():
                continue
            try:
                arqs = [f for f in os.listdir(p) if f.endswith(".jsonl")]
            except Exception:
                arqs = []
            rel = f"{nome_base}/{item}"
            if not arqs:
                violacoes.append(f"{rel}: pasta VAZIA (lixo)")
            elif len(arqs) > MAX_FILES_POR_PASTA:
                violacoes.append(
                    f"{rel}: {len(arqs)} arquivos (> {MAX_FILES_POR_PASTA}, regra de ouro)")
    return violacoes


def resumo_regras() -> str:
    """Resumo legível para o chat/status."""
    v = verificar_organizacao()
    if not v:
        return "Regras de ouro de organização: OK. (nenhuma violação)"
    return ("Regras de ouro VIOLADAS (" + str(len(v)) + "):\n"
            + "\n".join("• " + x for x in v))


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(resumo_regras())
