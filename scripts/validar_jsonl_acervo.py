#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
validar_jsonl_acervo.py — Valida a integridade do acervo JSONL em dados/processed/jsonl.

Para cada subpasta, lê uma amostra de arquivos e valida que cada linha é JSON
válido. Reporta: total de pastas, arquivos, linhas, erros encontrados e
duplicatas exatas (mesmo MD5) dentro da mesma pasta.

Uso:
  python scripts/validar_jsonl_acervo.py                 # valida tudo (amostra)
  python scripts/validar_jsonl_acervo.py --completo      # valida todas as linhas
  python scripts/validar_jsonl_acervo.py --pasta NOME    # valida uma pasta só
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
JSONL_DIR = PROJETO_ROOT / "dados" / "processed" / "jsonl"

AMOSTRA_LINHAS = 200  # linhas validadas por arquivo (modo amostra)


def _validar_linhas(arquivo: Path, completo: bool) -> tuple[int, int, list[str]]:
    """Valida as linhas de um arquivo jsonl. Retorna (linhas_ok, linhas_erro, erros)."""
    ok = 0
    erros = 0
    msgs: list[str] = []
    limite = None if completo else AMOSTRA_LINHAS
    try:
        with arquivo.open("r", encoding="utf-8") as f:
            for i, linha in enumerate(f, 1):
                if limite is not None and i > limite:
                    break
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    json.loads(linha)
                    ok += 1
                except json.JSONDecodeError as e:
                    erros += 1
                    if len(msgs) < 5:
                        msgs.append(f"linha {i}: {e}")
    except Exception as e:
        return 0, 1, [f"falha ao abrir: {e}"]
    return ok, erros, msgs


def _md5(arquivo: Path) -> str:
    h = hashlib.md5()
    with arquivo.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _duplicatas_na_pasta(pasta: Path) -> list[tuple[str, str]]:
    """Retorna pares de arquivos com mesmo conteúdo (MD5) dentro da pasta."""
    arquivos = sorted(pasta.glob("*.jsonl"))
    hashes: dict[str, list[Path]] = {}
    for a in arquivos:
        try:
            hashes.setdefault(_md5(a), []).append(a)
        except Exception:
            pass
    dups = []
    for grupo in hashes.values():
        if len(grupo) > 1:
            base = grupo[0]
            for outro in grupo[1:]:
                dups.append((base.name, outro.name))
    return dups


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida o acervo JSONL.")
    ap.add_argument("--completo", action="store_true", help="valida todas as linhas (mais lento)")
    ap.add_argument("--pasta", help="valida apenas uma subpasta")
    args = ap.parse_args()

    if not JSONL_DIR.exists():
        print(f"ERRO: pasta não encontrada: {JSONL_DIR}")
        return 1

    pastas = [JSONL_DIR / args.pasta] if args.pasta else sorted(
        [p for p in JSONL_DIR.iterdir() if p.is_dir()])
    if args.pasta and not pastas[0].exists():
        print(f"ERRO: pasta não encontrada: {pastas[0]}")
        return 1

    total_arq = total_ok = total_erro = 0
    problemas: list[str] = []
    print(f"{'Pasta':<45} {'Arq':>5} {'OK':>8} {'Erro':>5}  Detalhe")
    print("-" * 90)
    for pasta in pastas:
        arquivos = sorted(pasta.glob("*.jsonl"))
        if not arquivos:
            problemas.append(f"[VAZIA] {pasta.name} (sem arquivos)")
            print(f"{pasta.name:<45} {0:>5} {'-':>8} {'-':>5}  SEM ARQUIVOS")
            continue
        p_ok = p_erro = 0
        for a in arquivos:
            ok, erro, msgs = _validar_linhas(a, args.completo)
            p_ok += ok
            p_erro += erro
            if erro:
                problemas.append(f"[ERRO] {pasta.name}/{a.name}: {'; '.join(msgs[:2])}")
        dups = _duplicatas_na_pasta(pasta)
        total_arq += len(arquivos)
        total_ok += p_ok
        total_erro += p_erro
        detalhe = ""
        if dups:
            detalhe = f"DUPLICATAS: {len(dups)} par(es)"
        if p_erro:
            detalhe = (detalhe + " " + "ERROS DE JSON").strip()
        print(f"{pasta.name:<45} {len(arquivos):>5} {p_ok:>8} {p_erro:>5}  {detalhe}")

    print("-" * 90)
    print(f"TOTAL: {len(pastas)} pastas | {total_arq} arquivos | "
          f"{total_ok} linhas ok | {total_erro} linhas com erro")
    if problemas:
        print("\n[ATENCAO] PROBLEMAS ENCONTRADOS:")
        for p in problemas:
            print(f"  - {p}")
        return 2
    print("\n[OK] Acervo JSONL integro (amostra).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
