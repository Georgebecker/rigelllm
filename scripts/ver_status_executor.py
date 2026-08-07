# -*- coding: utf-8 -*-
"""Verifica se o status da API expõe o progresso (para a barra do painel)."""
import json, sys, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get(url, t=20, p=3):
    for i in range(t):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=10).read())
        except Exception:
            if i == t - 1:
                return None
            time.sleep(p)

B = 'http://127.0.0.1:8000'
st = get(B + '/api/executor/status')
if not st:
    print('FALHOU status')
    sys.exit(1)
print('rodando=', st.get('rodando'), '| total=', st.get('total'))
for a in st.get('atividades', []):
    p = a.get('progresso') or {}
    print(f"  - {a.get('nome')} -> {a.get('status')} | "
          f"pct={p.get('pct')}% | lidas={p.get('lidas')} | "
          f"ok={p.get('ok')} | descartados={p.get('descartados')}")
