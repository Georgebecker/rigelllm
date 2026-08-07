# -*- coding: utf-8 -*-
"""diag_servidores.py — Diagnóstico dos processos uvicorn e resposta HTTP."""
import sys, time, urllib.request
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== Processos uvicorn (com idade e CPU) ===")
agora = time.time()
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "cpu_percent", "status"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "uvicorn" in cl.lower() or "dashboard.main" in cl:
            idade = (agora - p.info["create_time"]) / 60
            print(f"PID {p.info['pid']} | status={p.info['status']} | "
                  f"idade={idade:.0f}min | cpu={p.info['cpu_percent']}% | {cl[:110]}")
    except Exception:
        pass

print()
print("=== HTTP test com detalhe ===")
for porta in (8000, 8001):
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/executor/status", timeout=5)
        print(f"{porta}: HTTP {req.status}")
    except Exception as e:
        print(f"{porta}: {type(e).__name__}: {str(e)[:160]}")
