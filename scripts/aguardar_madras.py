#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""aguardar_madras.py — monitora a sanitização Madras1 v2 até terminar e reporta."""
import json, os, sys, time, psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROG = r"d:\Projetos\rigelllm\logs\limpeza_progresso.json"
REPORT = r"d:\Projetos\rigelllm\dados\processed\limpo_madras1_v2\limpeza_relatorio.json"
# O relatório do run COMPLETO (iniciado 20:54 em 05/08) será mais novo que isto.
# O relatório da amostra 50k tinha gerado_em 2026-08-05T20:47:33.
INICIO_FULL = "2026-08-05T21:00:00"


def limpeza_rodando():
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if "limpeza_leve_rigel_v2" in " ".join(proc.info["cmdline"] or []):
                return True
        except Exception:
            pass
    return False


def progresso():
    if os.path.exists(PROG):
        try:
            with open(PROG, encoding="utf-8") as f:
                p = json.load(f)
            return (f"{p.get('lidos', 0)} lidos | {p.get('pct', 0)}% | "
                    f"{p.get('pretrain', 0)} pretrain | {p.get('descartados', 0)} descartados | "
                    f"atualizado {p.get('atualizado_em', '?')}")
        except Exception:
            pass
    return "sem progresso ainda"


print(f"[watcher] Iniciado {time.strftime('%H:%M:%S')} — aguardando término do Madras1 v2...", flush=True)
ultimo_print = time.time()
while True:
    if not limpeza_rodando():
        break
    try:
        if os.path.exists(REPORT):
            with open(REPORT, encoding="utf-8") as f:
                rel = json.load(f)
            if rel.get("gerado_em", "") > INICIO_FULL:
                break
    except Exception:
        pass
    agora = time.time()
    if agora - ultimo_print >= 300:  # atualização a cada 5 min
        print(f"[watcher] {time.strftime('%H:%M:%S')} | {progresso()}", flush=True)
        ultimo_print = agora
    time.sleep(20)

print(f"\n[watcher] FINAL {time.strftime('%H:%M:%S')} | {progresso()}", flush=True)
if os.path.exists(REPORT):
    try:
        with open(REPORT, encoding="utf-8") as f:
            rel = json.load(f)
        print("[watcher] RELATORIO FINAL:")
        print(json.dumps(rel, ensure_ascii=False, indent=2))
    except Exception as e:
        print("[watcher] erro lendo relatorio:", e)
