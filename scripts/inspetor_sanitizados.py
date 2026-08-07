# -*- coding: utf-8 -*-
"""Inspeciona os arquivos gerados pelo gerar_sanitizados.py (relatório + amostra)."""
import sys, json, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print('=== RELATORIO ===')
if os.path.exists('logs/sanitizacao_relatorio.json'):
    r = json.load(open('logs/sanitizacao_relatorio.json', encoding='utf-8'))
    print('  gerado_em:', r.get('gerado_em'))
    print('  origem:', r.get('origem'))
    print('  contadores:', r.get('contadores'))
    print('  gravados:', r.get('gravados'), '| taxa_descarte:', r.get('taxa_descarte'))
    print('  aviso_descarte_alto:', r.get('aviso_descarte_alto'))

print()
print('=== ARQUIVOS GERADOS ===')
pasta = 'dados/sanitizados'
for f in sorted(os.listdir(pasta)):
    p = os.path.join(pasta, f)
    n = sum(1 for _ in open(p, encoding='utf-8')) if os.path.isfile(p) else 0
    print(f'  {f}  ({os.path.getsize(p)/1e6:.1f} MB, {n} linhas)')

print()
print('=== AMOSTRA rigelsanitizado01.jsonl (5 exemplos) ===')
with open('dados/sanitizados/rigelsanitizado01.jsonl', encoding='utf-8') as f:
    for i, linha in enumerate(f):
        if i >= 5:
            break
        obj = json.loads(linha)
        msgs = obj.get('messages', [])
        users = [m['content'] for m in msgs if m.get('role') == 'user']
        ass = [m['content'] for m in msgs if m.get('role') == 'assistant']
        u = users[0][:90] if users else '(sem user)'
        a = ass[0][:90] if ass else '(sem assistant)'
        print(f'  [{i+1}] U: {u}')
        print(f'      A: {a}')
