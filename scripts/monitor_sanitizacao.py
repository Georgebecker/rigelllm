# -*- coding: utf-8 -*-
"""Monitora a sanitização em background até concluir."""
import json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

t0 = time.time()
while time.time() - t0 < 600:  # até 10 min
    time.sleep(10)
    if os.path.exists('estado/sanitizacao_estado.json'):
        d = json.load(open('estado/sanitizacao_estado.json', encoding='utf-8'))
        if not d.get('rodando'):
            print('CONCLUIDO:', d.get('status'))
            break
        arq = d.get('arquivo_atual') or ''
        print(f'  ... {int(time.time()-t0)}s | {arq[:40]} | '
              f'lidas={d.get("total_lidas")} ok={d.get("total_ok")} '
              f'descartados={d.get("total_descartados")}')

d = json.load(open('estado/sanitizacao_estado.json', encoding='utf-8'))
print('FINAL:', d.get('status'))
print('  lidas:', d.get('total_lidas'), '| ok:', d.get('total_ok'),
      '| corrigidos:', d.get('total_corrigidos'),
      '| descartados:', d.get('total_descartados'),
      '| nao_pt:', d.get('total_nao_pt'),
      '| gravados:', d.get('total_gravados'))
for e in d.get('eventos', [])[-3:]:
    print('  evento:', e.get('tipo'), '-', e.get('msg'))
