# -*- coding: utf-8 -*-
"""diag_chrome_drive.py — Verifica estado de Chrome, Google Drive e servidores."""
import sys, time, urllib.request
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

alvo_nomes = {
    "chrome.exe": "Google Chrome",
    "GoogleDriveFS.exe": "Google Drive",
    "GoogleDrive.exe": "Google Drive (legado)",
    "msedge.exe": "Edge",
}

print("=== Processos Chrome / Drive / Edge ===")
agora = time.time()
for p in psutil.process_iter(["pid", "name", "create_time", "status"]):
    try:
        nome = p.info["name"] or ""
        if nome.lower() in alvo_nomes:
            idade = (agora - p.info["create_time"]) / 60
            print(f"  {alvo_nomes.get(nome.lower(), nome)} | PID {p.info['pid']} | "
                  f"status={p.info['status']} | aberto há {idade:.0f} min")
    except Exception:
        pass

print()
print("=== Servidores uvicorn (8000/8001) ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "uvicorn" in cl.lower() or "dashboard.main" in cl:
            idade = (agora - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | status={p.info['status']} | idade={idade:.0f}min | {cl[:100]}")
    except Exception:
        pass

print()
print("=== Portas ===")
for porta in (8000, 8001):
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/executor/status", timeout=4)
        print(f"  {porta}: HTTP {req.status}")
    except Exception as e:
        print(f"  {porta}: {type(e).__name__}: {str(e)[:80]}")

print()
print("=== Processo 11080 (pai do PID 9952 que matei) — ainda existe? ===")
try:
    p = psutil.Process(11080)
    print(f"  11080: {p.name()} | {p.status()} | {' '.join(p.cmdline())[:120]}")
except Exception as e:
    print(f"  11080: NÃO existe mais ({type(e).__name__})")
