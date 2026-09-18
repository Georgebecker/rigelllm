#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
auditar_acervo.py — Auditoria de QUALIDADE do acervo por tipo (TXT e PARQUET).

Responde a pergunta do usuário (18/08): "os TXT/PARQUET foram reparados?
foram sanitizados? qual a situação?". Para cada pasta do acervo mede:
  - nº de arquivos e tamanho
  - MOJIBAKE REAL (duplo-encoding) em amostra de conteúdo
  - status: LIMPO / COM MOJIBAKE / VAZIO / ERRO

Amostral e leve (não varre o SSD inteiro):
  TXT     → lê até 5 arquivos x 50 linhas por pasta
  PARQUET → lê até 5 arquivos x 30 linhas por pasta (via pandas/pyarrow)

Uso:
  python scripts/auditar_acervo.py --tipo txt       # só TXT
  python scripts/auditar_acervo.py --tipo parquet   # só PARQUET
  python scripts/auditar_acervo.py                  # ambos
  python scripts/auditar_acervo.py --saida logs/auditoria_acervo.txt
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

# Garante UTF-8 no console (cp1252 do Windows)
for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJETO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = PROJETO_ROOT / "dados" / "processed"
TXT_DIR = PROCESSED / "txt"
PARQUET_DIR = PROCESSED / "parquet"
LOGS_DIR = PROJETO_ROOT / "logs"

# Mojibake REAL (duplo-encoding) — NÃO usar "Ã" solto (falso positivo: SÃO/MÃE)
_RE_MOJI = re.compile(r"Ã£|Ã©|Ãª|Ã§|Ã³|Ã¡|Ã­|Ã¼|Ã´|Ã¢|Ãµ|â€|â€œ|â€\u009d|\ufffd")

AMOSTRA_ARQUIVOS = 5
AMOSTRA_LINHAS = 50


def _checar_texto(texto: str) -> int:
    return len(_RE_MOJI.findall(texto))


def _auditar_pasta_txt(pasta: Path) -> dict:
    arqs = sorted(pasta.glob("*.txt"))
    if not arqs:
        return {"pasta": pasta.name, "tipo": "txt", "arquivos": 0, "mb": 0.0,
                "status": "VAZIO", "mojibake": 0, "linhas_checadas": 0}
    random.seed(42)
    amostra = random.sample(arqs, min(AMOSTRA_ARQUIVOS, len(arqs)))
    total_moji = 0
    linhas = 0
    for a in amostra:
        try:
            with a.open("r", encoding="utf-8", errors="replace") as f:
                for i, linha in enumerate(f):
                    if i >= AMOSTRA_LINHAS:
                        break
                    linhas += 1
                    total_moji += _checar_texto(linha)
        except Exception:
            pass
    tam = sum(a.stat().st_size for a in arqs)
    status = "LIMPO" if total_moji == 0 else "COM MOJIBAKE"
    return {"pasta": pasta.name, "tipo": "txt", "arquivos": len(arqs),
            "mb": round(tam / 1024 / 1024, 2), "status": status,
            "mojibake": total_moji, "linhas_checadas": linhas}


def _auditar_pasta_parquet(pasta: Path) -> dict:
    # rglob: pega .parquet em SUBPASTAS também (ex.: scrap tem parquet aninhado)
    arqs = sorted(pasta.rglob("*.parquet"))
    if not arqs:
        return {"pasta": pasta.name, "tipo": "parquet", "arquivos": 0,
                "mb": 0.0, "status": "VAZIO", "mojibake": 0, "colunas": []}
    try:
        import pandas as pd  # noqa: F401
    except Exception:
        return {"pasta": pasta.name, "tipo": "parquet", "arquivos": len(arqs),
                "mb": round(sum(a.stat().st_size for a in arqs) / 1024 / 1024, 2),
                "status": "SEM pandas (nao auditar)", "mojibake": -1, "colunas": []}
    total_moji = 0
    colunas: list[str] = []
    for a in arqs[:AMOSTRA_ARQUIVOS]:
        try:
            df = pd.read_parquet(a, engine="auto")
            if not colunas:
                colunas = [str(c) for c in df.columns]
            # amostra das colunas de texto (object OU string dtype — sem warning)
            for c in df.columns:
                dt = str(df[c].dtype)
                if dt not in ("object", "string") and not dt.startswith("str"):
                    continue
                amostra_txt = " ".join(str(x) for x in df[c].head(30).tolist())
                total_moji += _checar_texto(amostra_txt)
        except Exception as e:
            return {"pasta": pasta.name, "tipo": "parquet", "arquivos": len(arqs),
                    "mb": round(sum(x.stat().st_size for x in arqs) / 1024 / 1024, 2),
                    "status": f"ERRO ({type(e).__name__})", "mojibake": -1,
                    "colunas": []}
    status = "LIMPO" if total_moji == 0 else "COM MOJIBAKE"
    return {"pasta": pasta.name, "tipo": "parquet", "arquivos": len(arqs),
            "mb": round(sum(a.stat().st_size for a in arqs) / 1024 / 1024, 2),
            "status": status, "mojibake": total_moji, "colunas": colunas}


def _emitir(texto: str) -> None:
    """Imprime com FLUSH (streaming) — o painel/executor vê em tempo real."""
    print(texto, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Auditoria de qualidade do acervo (TXT/PARQUET).")
    ap.add_argument("--tipo", choices=["txt", "parquet"], help="só um tipo")
    ap.add_argument("--saida", help="arquivo de saída do relatório")
    args = ap.parse_args()

    linhas: list[str] = []
    linhas.append("AUDITORIA DO ACERVO (TXT e PARQUET)")
    linhas.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    linhas.append("-" * 90)
    _emitir(linhas[0])
    _emitir(linhas[1])
    _emitir(linhas[2])

    resultados: list[dict] = []
    if args.tipo in (None, "txt") and TXT_DIR.is_dir():
        pastas = sorted([p for p in TXT_DIR.iterdir() if p.is_dir()])
        _emitir(f"\n== TXT ({len(pastas)} pastas em processed/txt/) ==")
        _emitir(f"{'Pasta':<40} {'Arq':>6} {'MB':>8}  {'Status':<16} mojibake(amostra)")
        for i, p in enumerate(pastas, 1):
            r = _auditar_pasta_txt(p)
            resultados.append(r)
            linha = f"{r['pasta']:<40} {r['arquivos']:>6} {r['mb']:>8.1f}  " \
                    f"{r['status']:<16} {r['mojibake']}"
            linhas.append(linha)
            _emitir(f"[{i}/{len(pastas)}] " + linha)

    if args.tipo in (None, "parquet") and PARQUET_DIR.is_dir():
        pastas = sorted([p for p in PARQUET_DIR.iterdir() if p.is_dir()])
        _emitir(f"\n== PARQUET ({len(pastas)} pastas em processed/parquet/) ==")
        _emitir(f"{'Pasta':<40} {'Arq':>6} {'MB':>8}  {'Status':<22} colunas")
        for i, p in enumerate(pastas, 1):
            r = _auditar_pasta_parquet(p)
            resultados.append(r)
            linha = f"{r['pasta']:<40} {r['arquivos']:>6} {r['mb']:>8.1f}  " \
                    f"{r['status']:<22} {','.join(r.get('colunas', []))[:40]}"
            linhas.append(linha)
            _emitir(f"[{i}/{len(pastas)}] " + linha)

    # Resumo
    linhas.append("\n" + "-" * 90)
    for tipo in ("txt", "parquet"):
        rs = [r for r in resultados if r["tipo"] == tipo]
        if not rs:
            continue
        limpos = sum(1 for r in rs if r["status"] == "LIMPO")
        sujos = sum(1 for r in rs if r["status"] == "COM MOJIBAKE")
        vazios = sum(1 for r in rs if r["status"] == "VAZIO")
        erros = len(rs) - limpos - sujos - vazios
        linhas.append(f"{tipo.upper()}: {len(rs)} pastas | LIMPO={limpos} "
                      f"COM_MOJIBAKE={sujos} VAZIO={vazios} OUTROS={erros}")

    texto = "\n".join(linhas) + "\n"
    saida = Path(args.saida) if args.saida else LOGS_DIR / "auditoria_acervo.txt"
    saida.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"Relatorio salvo em: {saida}")

    # Salva dados estruturados
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGS_DIR / "auditoria_acervo.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
