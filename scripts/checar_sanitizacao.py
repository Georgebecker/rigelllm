# -*- coding: utf-8 -*-
"""Verifica estado da sanitização após o terminal ser fechado."""
import glob, json, os, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

arqs = sorted(glob.glob('dados/sanitizados/*.jsonl'))
print('Arquivos gerados:', len(arqs))
tot = 0
for a in arqs:
    n = sum(1 for _ in open(a, encoding='utf-8'))
    tot += n
print('Total linhas (última passada):', tot)

# Processos gerar_sanitizados vivos?
r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*gerar_sanitizados*' } | "
     "Select-Object -ExpandProperty ProcessId"],
    capture_output=True, text=True, timeout=30)
pids = [x for x in r.stdout.split() if x.isdigit()]
print('PIDs gerar_sanitizados vivos:', pids or 'NENHUM')

# Relatório persistido?
if os.path.exists('logs/sanitizacao_relatorio.json'):
    d = json.load(open('logs/sanitizacao_relatorio.json', encoding='utf-8'))
    print('Relatório mais recente:', d.get('gerado_em'), '| origem:', d.get('origem'))
