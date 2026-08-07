# -*- coding: utf-8 -*-
"""Diagnóstico visual do estado real (processos, porta, executor)."""
import json, os, subprocess, sys, psutil
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print('=== PROCESSOS uvicorn (quantos brigando pela porta?) ===')
for p in psutil.process_iter(['pid', 'status']):
    try:
        cl = ' '.join(p.cmdline())
        if 'uvicorn' in cl:
            print(f'  PID {p.pid} | {p.status()} | {cl[:90]}')
    except Exception:
        pass

print()
print('=== PORTA 8000 ===')
r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=30)
for l in r.stdout.splitlines():
    if ':8000' in l and 'LISTENING' in l:
        print(' ', l.strip())

print()
print('=== ESTADO executor persistido ===')
if os.path.exists('estado/executor_estado.json'):
    d = json.load(open('estado/executor_estado.json', encoding='utf-8'))
    for aid, a in d.items():
        print(f'  {aid} | {a.get("nome")} | {a.get("status")} | pid={a.get("pid")}')
else:
    print('  (sem arquivo)')

print()
print('=== PROCESSOS gerar_sanitizados ===')
for p in psutil.process_iter(['pid', 'status']):
    try:
        cl = ' '.join(p.cmdline())
        if 'gerar_sanitizados' in cl:
            print(f'  PID {p.pid} | {p.status()} | {cl[:90]}')
    except Exception:
        pass
