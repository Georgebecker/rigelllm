#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
auditar_dashboard.py - Auditoria de rotas do dashboard (FastAPI).
Versão: 1.0.0 | Data: 07/08/2026

Testa TODAS as rotas GET do OpenAPI + páginas HTML conhecidas e grava um
relatório em docs/AUDITORIA_ROTAS_GET.txt (cada linha: status | tempo | rota).

Uso: python scripts/auditar_dashboard.py [--base http://localhost:8000] [--timeout 6]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
OPENAPI = PROJETO / "openapi_dump.json"
RELATORIO = PROJETO / "docs" / "AUDITORIA_ROTAS_GET.txt"

# Páginas HTML (rotas de tela) que devem responder 200 rápido
PAGINAS = [
    "/", "/datasets", "/treino_local", "/treinamento", "/gerar_local", "/chat",
    "/converter", "/executor", "/debate", "/topicos", "/treino_colab",
    "/treino_colab_txt", "/tratamento", "/dados", "/scrap", "/logs",
]


def testar(url: str, timeout: float) -> tuple[int | str, float]:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "auditoria"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t0
    except Exception as e:
        return f"{type(e).__name__}", time.time() - t0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Audita rotas GET do dashboard")
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=6.0)
    args = parser.parse_args()

    if not OPENAPI.exists():
        print(f"❌ OpenAPI não encontrado: {OPENAPI} (baixe de {args.base}/openapi.json)")
        return 1

    spec = json.loads(OPENAPI.read_text(encoding="utf-8-sig"))
    rotas = [p for p, m in spec.get("paths", {}).items() if "get" in m]
    total = len(rotas) + len(PAGINAS)

    linhas: list[str] = []
    problemas: list[str] = []
    ok = nok = 0

    print(f"🔎 Auditando {len(rotas)} rotas GET + {len(PAGINAS)} páginas (timeout {args.timeout}s)...")

    alvos = [(f"/api{'' if p.startswith('/api') else ''}{p}" if not p.startswith('/') else p) for p in rotas]
    # normaliza: paths do openapi já começam com /
    alvos = [p for p in rotas] + PAGINAS

    # Salva incrementalmente a cada rota (mesmo que o script seja morto,
    # o relatório parcial fica e dá para ver onde parou / qual rota travou).
    def _salvar(parcial: bool = False):
        RELATORIO.parent.mkdir(parents=True, exist_ok=True)
        with open(RELATORIO, "w", encoding="utf-8") as f:
            f.write(f"# Auditoria de rotas GET — {time.strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"OK: {ok} | PROBLEMAS: {nok} | Total testado: {len(linhas)}\n")
            if parcial:
                f.write(f"# ⚠️ PARCIAL — parou na rota {i}/{total}\n")
            f.write("\n## Problemas\n")
            for p in problemas:
                f.write("- " + p + "\n")
            f.write("\n## Completo\n")
            for l in linhas:
                f.write(l + "\n")

    try:
        for i, path in enumerate(alvos, 1):
            url = args.base + path
            status, dt = testar(url, args.timeout)
            status_str = str(status)
            if status_str == "200":
                ok += 1
            else:
                nok += 1
                problemas.append(f"{status_str} | {dt:5.1f}s | GET {path}")
            linhas.append(f"{status_str} | {dt:5.1f}s | GET {path}")
            if i % 10 == 0 or i == total:
                print(f"  ... {i}/{total} (problemas: {nok})", flush=True)
                _salvar(parcial=True)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário — salvando parcial...", flush=True)
        _salvar(parcial=True)
        return 130
    except Exception as e:
        print(f"\nERRO no loop: {e} — salvando parcial...", flush=True)
        _salvar(parcial=True)
        return 1

    _salvar()
    print(f"\n✅ OK: {ok} | ⚠️ Problemas: {nok}")
    print(f"Relatório: {RELATORIO}")
    if problemas:
        print("\nProblemas:")
        for p in problemas:
            print("  - " + p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
