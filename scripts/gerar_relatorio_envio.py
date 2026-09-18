#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gerar_relatorio_envio.py — Gera relatório de envio do acervo JSONL para o Google Drive.

Varre dados/processed/jsonl, classifica as pastas em:
  [OK] LIMPAS (_sanitizado)  -> material de treino pronto
  [!] BRUTAS (sem _sanitizado) -> material cru que ainda precisa de tratamento
E gera um arquivo de texto organizado (logs/relatorio_envio_jsonl_AAAAMMDD.txt)
com tamanhos, prioridade e avisos de duplicata (pares bruto+limpo).

Uso:
  python scripts/gerar_relatorio_envio.py
  python scripts/gerar_relatorio_envio.py --saida docs/relatorio_envio.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Garante UTF-8 no console (cp1252 do Windows quebra com emojis/acentos)
for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJETO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = PROJETO_ROOT / "dados" / "processed"
JSONL_DIR = PROCESSED / "jsonl"
TXT_DIR = PROCESSED / "txt"
PARQUET_DIR = PROCESSED / "parquet"
TRATADOS_DIR = PROJETO_ROOT / "dados" / "tratados"
LOGS_DIR = PROJETO_ROOT / "logs"


def _tamanho(pasta: Path) -> tuple[int, int]:
    """Retorna (bytes, num_arquivos) dos arquivos DIRETOS de uma subpasta."""
    total = 0
    n = 0
    try:
        for a in pasta.iterdir():
            if a.is_file():
                total += a.stat().st_size
                n += 1
    except Exception:
        pass
    return total, n


def _fmt(mb: float) -> str:
    if mb >= 1024:
        return f"{mb/1024:.2f} GB"
    return f"{mb:.1f} MB"


def _secao_pastas(base: Path) -> list[tuple[str, int, int]]:
    """Lista (nome, arquivos, bytes) das subpastas de base com conteúdo."""
    itens: list[tuple[str, int, int]] = []
    if not base.is_dir():
        return itens
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        tam, n = _tamanho(p)
        if tam == 0:
            continue
        itens.append((p.name, n, tam))
    itens.sort(key=lambda x: -x[2])
    return itens


def main() -> int:
    ap = argparse.ArgumentParser(description="Relatório de envio do acervo ao Google Drive.")
    ap.add_argument("--saida", help="caminho do arquivo de saída")
    args = ap.parse_args()

    linhas: list[str] = []
    linhas.append("=" * 72)
    linhas.append("RELATÓRIO DE ENVIO — ACERVO PARA GOOGLE DRIVE (por tipo)")
    linhas.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    linhas.append("=" * 72)
    linhas.append("")

    # ── JSONL ──────────────────────────────────────────────────────────────
    limpas: list[tuple[str, int, int]] = []
    brutas: list[tuple[str, int, int]] = []
    for nome, n, tam in _secao_pastas(JSONL_DIR):
        (limpas if nome.endswith("_sanitizado") else brutas).append((nome, n, tam))
    tot_limpo = sum(t for _, _, t in limpas)
    tot_bruto = sum(t for _, _, t in brutas)

    linhas.append("=" * 72)
    linhas.append("FASE 1 — JSONL (dados/processed/jsonl)")
    linhas.append("=" * 72)
    linhas.append(f"  Total: {len(limpas) + len(brutas)} pastas | "
                  f"{_fmt((tot_limpo + tot_bruto)/1024/1024)}")
    linhas.append(f"  [OK] Limpas (_sanitizado): {len(limpas)} pastas = {_fmt(tot_limpo/1024/1024)}")
    linhas.append(f"  [!] Brutas (sem _sanitizado): {len(brutas)} pastas = {_fmt(tot_bruto/1024/1024)}")
    for nome, n, tam in limpas + brutas:
        flag = "[OK]" if nome.endswith("_sanitizado") else "[!]"
        linhas.append(f"  {flag} [{(tam/1024/1024):>10.1f} MB] {nome:<45} ({n} arq)")
    for nome, _, _ in brutas:
        if (JSONL_DIR / f"{nome}_sanitizado").exists():
            linhas.append(f"     [DUP] duplicata: {nome} ja tem versao limpa - envie so a limpa")
    linhas.append("")

    # ── PARQUET ────────────────────────────────────────────────────────────
    parq = _secao_pastas(PARQUET_DIR)
    tot_parq = sum(t for _, _, t in parq)
    linhas.append("=" * 72)
    linhas.append(f"FASE 2 — PARQUET (dados/processed/parquet) — {len(parq)} pastas = "
                  f"{_fmt(tot_parq/1024/1024)}")
    linhas.append("=" * 72)
    for nome, n, tam in parq:
        linhas.append(f"  [{(tam/1024/1024):>10.1f} MB] {nome:<45} ({n} arq)")
    linhas.append("")

    # ── TXT ────────────────────────────────────────────────────────────────
    txts = _secao_pastas(TXT_DIR)
    tot_txt = sum(t for _, _, t in txts)
    linhas.append("=" * 72)
    linhas.append(f"FASE 3 — TXT (dados/processed/txt) — {len(txts)} pastas = "
                  f"{_fmt(tot_txt/1024/1024)}")
    linhas.append("=" * 72)
    for nome, n, tam in txts[:60]:
        linhas.append(f"  [{(tam/1024/1024):>10.1f} MB] {nome:<45} ({n} arq)")
    if len(txts) > 60:
        linhas.append(f"  ... + {len(txts) - 60} pastas menores")
    linhas.append("")

    # ── TRATADOS ───────────────────────────────────────────────────────────
    trat = _secao_pastas(TRATADOS_DIR)
    tot_trat = sum(t for _, _, t in trat)
    linhas.append("=" * 72)
    linhas.append(f"EXTRA — TRATADOS (dados/tratados) — material bruto já tratado = "
                  f"{_fmt(tot_trat/1024/1024)}")
    linhas.append("=" * 72)
    for nome, n, tam in trat:
        linhas.append(f"  [{(tam/1024/1024):>10.1f} MB] {nome:<45} ({n} arq)")
    linhas.append("")

    # ── Resumo ─────────────────────────────────────────────────────────────
    grand_total = tot_limpo + tot_bruto + tot_parq + tot_txt + tot_trat
    linhas.append("=" * 72)
    linhas.append(f"GRANDE TOTAL do acervo: {_fmt(grand_total/1024/1024)}")
    linhas.append("=" * 72)

    texto = "\n".join(linhas) + "\n"
    saida = Path(args.saida) if args.saida else LOGS_DIR / f"relatorio_envio_{datetime.now():%Y%m%d}.txt"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"\nRelatorio salvo em: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
