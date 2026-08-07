# -*- coding: utf-8 -*-
"""diag_duplicado.py — Verifica os 2 processos limpeza_leve em detalhe."""
import sys, time
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== Detalhes dos processos limpeza_leve ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "cpu_percent", "memory_info", "ppid"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "limpeza_leve" in cl:
            idade = (time.time() - p.info["create_time"]) / 60
            mem = (p.info["memory_info"].rss or 0) / 1e6
            cpu = p.info["cpu_percent"] or 0
            print(f"  PID {p.info['pid']} | pai={p.info['ppid']} | idade={idade:.0f}min | "
                  f"RAM {mem:.0f}MB | CPU {cpu:.1f}%")
            print(f"    cmd: {cl}")
            print()
    except Exception:
        pass
