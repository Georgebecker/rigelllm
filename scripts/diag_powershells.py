# -*- coding: utf-8 -*-
"""diag_powershells.py — Lista PowerShells/Python/llama abertos com idade e cmdline."""
import sys, time
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

agora = time.time()
print("=== PowerShells abertos ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
    try:
        nome = (p.info["name"] or "").lower()
        if "powershell" in nome or "pwsh" in nome or nome in ("cmd.exe", "conhost.exe"):
            cl = " ".join(p.info["cmdline"] or [])[:110]
            idade = (agora - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | {p.info['name']} | {idade:.0f}min | {cl}")
    except Exception:
        pass

print()
print("=== Python / llama / uvicorn abertos ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
    try:
        nome = (p.info["name"] or "").lower()
        cl = " ".join(p.info["cmdline"] or [])
        if "python" in nome or "llama" in nome or "uvicorn" in cl.lower():
            idade = (agora - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | {p.info['name']} | {idade:.0f}min | {cl[:120]}")
    except Exception:
        pass
