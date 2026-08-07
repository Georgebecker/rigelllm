# -*- coding: utf-8 -*-
"""diag_cpu_telemetria.py — Top consumidores de CPU + estado da telemetria do Windows."""
import sys, time
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== Top 15 processos por CPU (amostra 1s) ===")
# Primeira chamada de cpu_percent retorna 0 — pré-aquece
for p in psutil.process_iter(["pid", "name"]):
    try:
        p.cpu_percent(None)
    except Exception:
        pass
time.sleep(1.0)

linhas = []
for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
    try:
        linhas.append((p.info["cpu_percent"] or 0, p.info["name"], p.info["pid"],
                       p.info["memory_percent"] or 0))
    except Exception:
        pass
linhas.sort(reverse=True)
for cpu, nome, pid, mem in linhas[:15]:
    print(f"  {cpu:5.1f}% CPU | {mem:4.1f}% RAM | PID {pid} | {nome}")

print()
print("=== Serviços de telemetria/diagnóstico do Windows ===")
import subprocess
alvos = ["DiagTrack", "dmwappushservice", "WMPNetworkSvc", "SysMain",
         "WSearch", "MapsBroker", "diagnosticshub.standardcollector.set",
         "DPS", "WdiServiceHost"]
for svc in alvos:
    try:
        r = subprocess.run(["sc", "query", svc],
                           capture_output=True, text=True, timeout=10)
        estado = "?"
        for ln in r.stdout.splitlines():
            if "STATE" in ln or "ESTADO" in ln:
                estado = ln.split(":", 1)[1].strip()
        print(f"  {svc}: {estado}")
    except Exception as e:
        print(f"  {svc}: erro {type(e).__name__}")
