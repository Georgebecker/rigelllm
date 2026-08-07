# -*- coding: utf-8 -*-
"""Testa streaming/progresso do executor: inicia sanitização e acompanha o pct."""
import json, sys, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get(url, t=25, p=3):
    for i in range(t):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=10).read())
        except Exception:
            if i == t - 1:
                raise
            time.sleep(p)

def post(url, corpo, t=25, p=3):
    for i in range(t):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(corpo).encode(),
                headers={'Content-Type': 'application/json'})
            return json.loads(urllib.request.urlopen(req, timeout=15).read())
        except Exception:
            if i == t - 1:
                raise
            time.sleep(p)

B = 'http://127.0.0.1:8000'
post(B + '/api/executor/limpar-historico', {})
r = post(B + '/api/executor/iniciar', {
    'comando': 'sanitizar',
    'origem': 'dados/processed/jsonl/rigeljsonl_20260802_0136',
    'args': ['--max-arquivos', '30'],
    'nome': 'san-stream-teste'})
print('iniciar:', r.get('ok'), r.get('id'))
aid = r.get('id')

for t in range(8):
    time.sleep(4)
    one = get(B + '/api/executor/status?aid=' + aid) if aid else {}
    prog = one.get('progresso') or {}
    print(f"  t={t*4}s | status={one.get('status')} | "
          f"pct={prog.get('pct')}% | lidas={prog.get('lidas')} | "
          f"ok={prog.get('ok')} | descartados={prog.get('descartados')} | "
          f"linhas_sse={len(one.get('mensagens', []))}")
    if not one.get('rodando'):
        break
