#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
monitor_download.py — Watcher do download/explosão de datasets do dashboard.

Verifica a cada INTERVALO segundos se o dataset.jsonl está crescendo e se o
status do dashboard mudou. Imprime um resumo a cada checagem e sai quando:
  • o download termina (rodando=False) — mostra o resultado final; ou
  • TRAVA (nada muda por PARADO_MAX verificações consecutivas) — alerta.

Uso:
  d:/Projetos/rigelllm/.venv/Scripts/python.exe scripts/monitor_download.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

ARQUIVO = r"d:\Projetos\rigelllm\dados\raw\Madras1_corpus-ptbr-v1\dataset.jsonl"
URL_STATUS = "http://127.0.0.1:8000/api/datasets/status"
INTERVALO = 60          # segundos entre checagens
PARADO_MAX = 3          # nº de checagens sem NENHUMA mudança = travado


def get_status() -> dict:
    try:
        with urllib.request.urlopen(URL_STATUS, timeout=6) as r:
            return json.load(r)
    except Exception as e:  # servidor reiniciando (reload) — não é travamento
        return {"rodando": None, "erro": str(e)}


def get_tam() -> int | None:
    try:
        return os.path.getsize(ARQUIVO)
    except OSError:
        return None


def _assinatura(st: dict, tam: int | None) -> tuple:
    return (st.get("etapa"), st.get("percentual"), st.get("total_exemplos"),
            st.get("total_arquivos"), st.get("total_pastas"), tam)


def main() -> None:
    print(f"[monitor] intervalo={INTERVALO}s | parado_max={PARADO_MAX} checagens | arquivo={ARQUIVO}",
          flush=True)
    tam_ant = None
    ass_ant = None
    parado = 0
    while True:
        st = get_status()
        tam = get_tam()
        hora = time.strftime("%H:%M:%S")
        mb = tam / 1024 / 1024 if tam else 0.0
        delta_mb = (tam - tam_ant) / 1024 / 1024 if (tam_ant is not None and tam is not None) else 0.0
        rodando = st.get("rodando")
        etapa = st.get("etapa")
        pct = st.get("percentual")
        print(f"[{hora}] dataset.jsonl={mb/1024:.2f} GB (Δ {delta_mb:+.1f} MB/min) | "
              f"status: {etapa} {pct}% | exemplos={st.get('total_exemplos')} "
              f"arqs={st.get('total_arquivos')} pastas={st.get('total_pastas')} | {st.get('mensagem','')[:50]}",
              flush=True)

        # Fim do fluxo
        if rodando is False:
            print(f"[{hora}] ✅ FLUXO TERMINOU — etapa={etapa} | exemplos={st.get('total_exemplos')} "
                  f"arquivos={st.get('total_arquivos')} pastas={st.get('total_pastas')} "
                  f"erro={st.get('erro')}", flush=True)
            return

        # Detecção de travamento: nada muda (assinatura igual) por N checagens
        if rodando is True:
            ass = _assinatura(st, tam)
            if ass == ass_ant:
                parado += 1
            else:
                parado = 0
            ass_ant = ass
            if parado >= PARADO_MAX:
                print(f"[{hora}] ⚠️ TRAVADO: nada mudou há {parado} checagens "
                      f"({parado * INTERVALO}s) na etapa '{etapa}'. Algo errado — "
                      f"propor apagar parcial, limpar registros/logs e re-baixar.", flush=True)
                return

        tam_ant = tam
        time.sleep(INTERVALO)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[monitor] interrompido pelo usuário")
        sys.exit(0)
