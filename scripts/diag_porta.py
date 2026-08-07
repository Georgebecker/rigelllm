# -*- coding: utf-8 -*-
"""Verifica PIDs da porta 8000 e processos relacionados (watchdog/uvicorn)."""
import psutil, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print('=== PIDs LISTENING na :8000 existem? ===')
r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=30)
pids_porta = set()
for l in r.stdout.splitlines():
    if ':8000' in l and 'LISTENING' in l:
        pid = l.strip().split()[-1]
        pids_porta.add(int(pid))
        print('  LISTENING PID:', pid)

for pid in pids_porta:
    try:
        p = psutil.Process(pid)
        cl = ' '.join(p.cmdline())
        print(f'  -> PID {pid} EXISTE | {p.name()} | cmd: {cl[:90]}')
    except psutil.NoSuchProcess:
        print(f'  -> PID {pid} NAO EXISTE (morto - netstat obsoleto)')
    except Exception as e:
        print(f'  -> PID {pid} erro: {e}')

print()
print('=== Processos run_dashboard/uvicorn vivos ===')
for p in psutil.process_iter(['pid', 'name', 'status']):
    try:
        cl = ' '.join(p.cmdline())
        if 'run_dashboard' in cl or 'uvicorn' in cl or 'activate.bat' in cl:
            print(f'  PID {p.pid} | {p.name()} | {p.status()} | {cl[:80]}')
    except Exception:
        pass
