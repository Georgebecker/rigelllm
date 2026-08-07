# -*- coding: utf-8 -*-
"""diag_profundidade.py — Busca profunda por Chrome/Drive + histórico de processos."""
import sys, time
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== Busca ampla: qualquer processo com google/chrome/drive no nome OU cmdline ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
    try:
        nome = (p.info["name"] or "").lower()
        cl = " ".join(p.info["cmdline"] or []).lower()
        if any(k in nome for k in ("chrome", "drive", "google")) or \
           any(k in cl for k in ("chrome", "google", "drive")):
            idade = (time.time() - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | {p.info['name']} | status={p.info['status']} | "
                  f"idade={idade:.0f}min | {cl[:100]}")
    except Exception:
        pass

print()
print("=== Chrome/Edge/Drive: TODOS os processos com esses nomes ===")
nomes = ["chrome.exe", "msedge.exe", "GoogleDriveFS.exe", "GoogleDrive.exe", "drive.exe", "googledrivesync.exe"]
for p in psutil.process_iter(["pid", "name", "create_time", "status"]):
    try:
        nome = (p.info["name"] or "").lower()
        if nome in nomes:
            idade = (time.time() - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | {p.info['name']} | status={p.info['status']} | idade={idade:.0f}min")
    except Exception:
        pass

print()
print("=== PIDs recentes que EU matei (9952, 19016, 11080) — o que eram ===")
for pid in (9952, 19016, 11080):
    try:
        p = psutil.Process(pid)
        print(f"  {pid}: AINDA VIVO: {p.name()} | {' '.join(p.cmdline())[:120]}")
    except psutil.NoSuchProcess:
        print(f"  {pid}: não existe mais (morto)")
    except Exception as e:
        print(f"  {pid}: erro {e}")

print()
print("=== Chrome está instalado? (procura o executável no caminho padrão) ===")
import os
caminhos = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]
for c in caminhos:
    print(f"  {c}: {'EXISTE' if os.path.exists(c) else 'não encontrado'}")
