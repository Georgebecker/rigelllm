#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
explodir_rigel.py — Explosão pelo MESMO motor do dashboard (REGRA DE OURO:
o dashboard informa tudo o que ocorre; o backend e o painel vivem em harmonia).

Usar ISSO no terminal (em vez de `createjsonl.py --process`) garante que o
painel "Explosão controlada" mostre estimativa, progresso, linha do tempo e o
resultado final — exatamente como o botão do dashboard.

Uso:
  python scripts/explodir_rigel.py <caminho|pasta> [--nome NOME] [--repo REPO] [--max-exemplos N]
  exemplo: python scripts/explodir_rigel.py dados/raw/Madras1_corpus-ptbr-v2 --nome Madras1_corpus-ptbr-v2
"""
from __future__ import annotations

import argparse
import os
import sys
import time

PROJETO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJETO_ROOT not in sys.path:
    sys.path.insert(0, PROJETO_ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description="Explode um dataset usando o motor do dashboard.")
    ap.add_argument("caminho", help="Arquivo ou pasta do dataset (ex.: dados/raw/<pasta>)")
    ap.add_argument("--nome", default="", help="Nome da pasta de saída em dados/gerados/jsonl/")
    ap.add_argument("--repo", default="", help="Repo HF (opcional)")
    ap.add_argument("--max-exemplos", type=int, default=None)
    args = ap.parse_args()

    from dashboard.services import explosao_local

    r = explosao_local.iniciar(args.caminho, repo=args.repo, nome=args.nome)
    if not r.get("ok"):
        print("ERRO:", r.get("erro"))
        return 1
    print(r.get("mensagem"))
    print("Acompanhe o progresso no dashboard: http://127.0.0.1:8000/datasets (painel Explosão controlada)")
    print()

    # Monitora até terminar (o dashboard também mostra isso)
    ultimo = ""
    try:
        while True:
            st = explosao_local.status()
            linha = (f"[{st.get('status')}] exemplos={st.get('total_exemplos')} "
                     f"arquivos={st.get('total_arquivos')} pastas={st.get('total_pastas')}")
            if linha != ultimo:
                print(linha, flush=True)
                ultimo = linha
            if not st.get("rodando"):
                break
            time.sleep(3)
    except KeyboardInterrupt:
        print("Ctrl+C — a explosão continua no dashboard; use Pausar/Parar lá.")
        return 0

    print()
    print("RESULTADO:", st.get("status"))
    if st.get("diagnostico"):
        d = st.get("diagnostico")
        print("DIAGNÓSTICO:", d.get("tipo"))
        print("MOTIVO:", d.get("motivo"))
        print("SUGESTÃO:", d.get("sugestao"))
    elif st.get("erro"):
        print("ERRO:", st.get("erro"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
