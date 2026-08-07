# -*- coding: utf-8 -*-
"""diag_consoles.py — Mapa de OpenConsole.exe + PowerShell com parentes e idade."""
import sys, time
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

agora = time.time()
print("=== OpenConsole.exe (hosts de terminal) ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
    try:
        if (p.info["name"] or "").lower() == "openconsole.exe":
            cl = " ".join(p.info["cmdline"] or [])[:80]
            idade = (agora - p.info["create_time"]) / 60
            try:
                pai = psutil.Process(p.ppid())
                pai_nome = pai.name()
                pai_cl = " ".join(pai.cmdline() or [])[:60]
            except Exception:
                pai_nome, pai_cl = "?", ""
            print(f"  PID {p.info['pid']} | {idade:.0f}min | pai={p.ppid()}({pai_nome}) | {cl}")
    except Exception:
        pass

print()
print("=== PowerShell (hosts de shell) ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
    try:
        if (p.info["name"] or "").lower() in ("powershell.exe", "pwsh.exe"):
            cl = " ".join(p.info["cmdline"] or [])[:100]
            idade = (agora - p.info["create_time"]) / 60
            try:
                pai = psutil.Process(p.ppid())
                pai_nome = pai.name()
            except Exception:
                pai_nome = "?"
            print(f"  PID {p.info['pid']} | {idade:.0f}min | pai={p.ppid()}({pai_nome}) | {cl}")
    except Exception:
        pass
