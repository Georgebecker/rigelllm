# -*- coding: utf-8 -*-
"""matar_telemetria.py — Mata CompatTelRunner.exe e confirma a CPU liberada."""
import sys, time
import psutil, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== CompatTelRunner.exe antes ===")
for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
    try:
        if (p.info["name"] or "").lower() == "compatteelrunner.exe" or \
           (p.info["name"] or "").lower() == "compatteelrunner.exe":
            pass
        if (p.info["name"] or "").lower() in ("compatteelrunner.exe", "compatteelrunner.exe"):
            pass
    except Exception:
        pass
# (o nome correto é CompatTelRunner.exe — busca case-insensitive por nome)
achou = 0
for p in psutil.process_iter(["pid", "name"]):
    try:
        nome = (p.info["name"] or "").lower()
        if "compatteelrunner" in nome or "compat" in nome and "runner" in nome:
            print(f"  PID {p.info['pid']} | {p.info['name']} | rodando")
            achou += 1
    except Exception:
        pass
if not achou:
    print("  (nenhum processo CompatTelRunner rodando agora)")

print()
print("=== Matando CompatTelRunner.exe (taskkill, sem /T) ===")
r = subprocess.run(
    ["taskkill", "/IM", "CompatTelRunner.exe", "/F"],
    capture_output=True, text=True, timeout=30)
print("  saída:", (r.stdout or r.stderr or "").strip())

print()
print("=== Confirmando CPU depois (amostra 2s) ===")
for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
    try:
        p.cpu_percent(None)
    except Exception:
        pass
time.sleep(2.0)
total = 0.0
for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
    try:
        nome = (p.info["name"] or "").lower()
        cpu = p.info["cpu_percent"] or 0
        total += cpu
        if "compat" in nome or ("compat" in nome and "runner" in nome):
            print(f"  {p.info['pid']} | {p.info['name']} | {cpu:.1f}% CPU")
    except Exception:
        pass
print(f"  CompatTelRunner ainda rodando? {'verificar acima'}")
print(f"  CPU total usada (todos processos): {total:.0f}%")
