#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
registrar_pastas.py — REGISTRA as pastas de treino por tipo (txt/jsonl/parquet)
e mostra o que enviar para cada pasta do Google Drive.

Uso:
    python scripts/registrar_pastas.py                    # todos os tipos
    python scripts/registrar_pastas.py --tipo jsonl       # só jsonl
    python scripts/registrar_pastas.py --tipo txt,parquet
    python scripts/registrar_pastas.py --saida logs/relatorio_registro.txt

O que faz:
  1. Varre dados/processed/<tipo>/ em busca de subpastas com arquivos do tipo;
  2. Atualiza registro_pastas_treino.json (com o campo 'tipo' em cada pasta) —
     os treinadores (treinoparquet, treinov2, treinar_com_jsonl) leem esse
     registro para ir DIRETO às pastas, sem escanear o acervo inteiro;
  3. Imprime o relatório: quais pastas enviar para cada pasta do Drive.

Segurança:
  - NUNCA apaga entradas do registro (só adiciona/atualiza);
  - NUNCA apaga dados — só leitura do acervo;
  - preserva 'vezes_treinada' e 'ultimo_treino' das entradas existentes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Garante import de regras_pastas.py (na raiz do projeto)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from regras_pastas import (  # noqa: E402
    PROJETO_ROOT,
    PROCESSED_TXT,
    PROCESSED_JSONL,
    PROCESSED_PARQUET,
    LIMITES_POR_TIPO,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REGISTRO_PATH = PROJETO_ROOT / "registro_pastas_treino.json"

BASES_POR_TIPO = {
    "txt": PROCESSED_TXT,
    "jsonl": PROCESSED_JSONL,
    "parquet": PROCESSED_PARQUET,
}

# Extensões aceitas por tipo (espelham o que os treinadores leem)
EXT_POR_TIPO = {
    "txt": (".txt",),
    "jsonl": (".jsonl", ".jsonl.gz", ".json", ".json.gz"),
    "parquet": (".parquet",),
}


def _contar(pasta: Path, exts: tuple) -> tuple[int, float]:
    """Conta arquivos com as extensões (recursivo) e soma o tamanho em MB."""
    total = 0
    mb = 0.0
    try:
        for raiz, _, arquivos in os.walk(pasta):
            for a in arquivos:
                if a.lower().endswith(exts):
                    total += 1
                    try:
                        mb += os.path.getsize(os.path.join(raiz, a)) / (1024 * 1024)
                    except OSError:
                        pass
    except OSError:
        pass
    return total, mb


def _registrar_tipo(tipo: str, registro: dict) -> list[dict]:
    """Varre a base do tipo, atualiza o registro (NO MESMO dict) e devolve as
    pastas achadas. IMPORTANTE: mexe em `registro["pastas"]` por referência —
    senão as mudanças se perdem na hora de salvar."""
    base = BASES_POR_TIPO[tipo]
    exts = EXT_POR_TIPO[tipo]

    # Garante que registro["pastas"] existe e é dict (defesa)
    if not isinstance(registro, dict):
        registro = {}
    pastas = registro.setdefault("pastas", {})
    if not isinstance(pastas, dict):
        pastas = {}
        registro["pastas"] = pastas
    # Remove entradas malformadas (defesa — nunca apaga pastas do disco)
    for k in [k for k, v in pastas.items() if not isinstance(v, dict)]:
        del pastas[k]

    if not base.is_dir():
        print(f"[{tipo}] Pasta base nao existe: {base}")
        return []

    achadas: list[dict] = []
    for item in sorted(os.listdir(base)):
        caminho = base / item
        if not caminho.is_dir():
            continue
        total, mb = _contar(caminho, exts)
        if total <= 0:
            continue
        info_antiga = pastas.get(item, {})
        # Barra NORMAL (/) no registro — funciona no Windows E no Linux (Colab)
        caminho_rel = os.path.relpath(caminho, PROJETO_ROOT).replace("\\", "/")
        pastas[item] = {
            "tipo": tipo,
            "caminho": caminho_rel,
            "arquivos": total,
            "mb": round(mb, 1),
            "vezes_treinada": info_antiga.get("vezes_treinada", 0),
            "ultimo_treino": info_antiga.get("ultimo_treino", ""),
        }
        achadas.append(pastas[item])
        print(f"[{tipo}] registrada: {caminho_rel} "
              f"({total} arquivo(s), {pastas[item]['mb']} MB)")

    if not achadas:
        print(f"[{tipo}] Nenhuma subpasta com arquivos do tipo em {base}")
    return achadas


def _imprimir_relatorio(por_tipo: dict) -> None:
    print("=" * 76)
    print("PASTAS PARA ENVIAR AO GOOGLE DRIVE (por tipo)")
    print(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 76)
    for tipo in ("txt", "jsonl", "parquet"):
        itens = por_tipo.get(tipo, [])
        if not itens:
            continue
        limite = LIMITES_POR_TIPO.get("." + tipo, 5000)
        print(f"\n[{tipo.upper()}]  (pasta '{tipo}' no Drive - "
              f"ate {limite} arquivos por pasta)")
        for it in sorted(itens, key=lambda x: x["caminho"]):
            print(f"  - {it['caminho']}  ({it['arquivos']} arquivo(s), "
                  f"{it['mb']} MB)")
        tot_arq = sum(i["arquivos"] for i in itens)
        tot_mb = sum(i["mb"] for i in itens)
        print(f"  TOTAL: {len(itens)} pasta(s) | {tot_arq} arquivo(s) | "
              f"{tot_mb:.1f} MB")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Registra as pastas de treino por tipo "
                    "(txt/jsonl/parquet) e lista o que enviar ao Drive.")
    ap.add_argument("--tipo", default="todos",
                    help="tipos a registrar: txt, jsonl, parquet ou 'todos' "
                         "(pode separar com virgula)")
    ap.add_argument("--registro", default=str(REGISTRO_PATH),
                    help="caminho do arquivo de registro")
    ap.add_argument("--saida", default=None,
                    help="tambem grava o relatorio em um arquivo .txt")
    args = ap.parse_args()

    bruto = (args.tipo or "").strip().lower()
    if bruto in ("todos", "all", "*"):
        tipos = ["txt", "jsonl", "parquet"]
    else:
        tipos = [t for t in re.split(r"[,;]", bruto)
                 if t in ("txt", "jsonl", "parquet")]
    if not tipos:
        print("Tipo invalido. Use: txt, jsonl, parquet ou 'todos'.")
        return 2

    try:
        with open(args.registro, "r", encoding="utf-8") as f:
            registro = json.load(f)
    except Exception:
        registro = {}
    if not isinstance(registro, dict) or "pastas" not in registro:
        registro = {"pastas": {}}

    por_tipo: dict = {}
    for t in tipos:
        por_tipo[t] = _registrar_tipo(t, registro)

    try:
        with open(args.registro, "w", encoding="utf-8") as f:
            json.dump({"pastas": registro.get("pastas", {})}, f,
                      ensure_ascii=False, indent=2)
        print(f"\nRegistro salvo em: {args.registro}")
    except Exception as e:
        print(f"AVISO: nao consegui salvar o registro: {e}")

    _imprimir_relatorio(por_tipo)

    if args.saida:
        try:
            linhas = [f"PASTAS PARA ENVIAR AO GOOGLE DRIVE (por tipo)",
                      f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                      "=" * 76]
            for tipo in ("txt", "jsonl", "parquet"):
                itens = por_tipo.get(tipo, [])
                if not itens:
                    continue
                linhas.append(f"\n[{tipo.upper()}]")
                for it in sorted(itens, key=lambda x: x["caminho"]):
                    linhas.append(f"  - {it['caminho']}  "
                                  f"({it['arquivos']} arquivo(s), {it['mb']} MB)")
                tot_arq = sum(i["arquivos"] for i in itens)
                tot_mb = sum(i["mb"] for i in itens)
                linhas.append(f"  TOTAL: {len(itens)} pasta(s) | "
                              f"{tot_arq} arquivo(s) | {tot_mb:.1f} MB")
            with open(args.saida, "w", encoding="utf-8") as f:
                f.write("\n".join(linhas))
            print(f"Relatorio tambem gravado em: {args.saida}")
        except Exception as e:
            print(f"AVISO: nao consegui gravar o relatorio: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
