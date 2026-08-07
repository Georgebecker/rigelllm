# -*- coding: utf-8 -*-
"""Testa o executor via API com retry robusto (aguarda reload estabilizar)."""
import json, sys, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get(url, tentativas=20, pausa=3):
    for t in range(tentativas):
        try:
            r = urllib.request.urlopen(url, timeout=10)
            return json.loads(r.read())
        except Exception as e:
            if t == tentativas - 1:
                raise
            time.sleep(pausa)

def post(url, corpo, tentativas=20, pausa=3):
    for t in range(tentativas):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(corpo).encode(),
                headers={'Content-Type': 'application/json'})
            r = urllib.request.urlopen(req, timeout=15)
            return json.loads(r.read())
        except Exception as e:
            if t == tentativas - 1:
                raise
            time.sleep(pausa)

BASE = 'http://127.0.0.1:8000'

print('inicial:', get(BASE + '/api/executor/status'))
r = post(BASE + '/api/executor/iniciar', {
    'comando': 'diagnostico_chars',
    'origem': 'dados/processed/jsonl/rigeljsonl43',
    'nome': 'diag-teste'})
print('iniciar:', r)
aid = r.get('id')
time.sleep(8)

st = get(BASE + '/api/executor/status')
print('global: rodando=', st.get('rodando'), 'total=', st.get('total'),
      'max=', st.get('max_concorrencia'))
for a in st.get('atividades', []):
    print('  -', a.get('id'), a.get('nome'), '->', a.get('status'),
          'pid', a.get('pid'))

if aid:
    one = get(BASE + '/api/executor/status?aid=' + aid)
    print('individual:', one.get('status'), '| exit:',
          one.get('exit_code'), '| linhas:', len(one.get('mensagens', [])))
    for l in one.get('mensagens', [])[:3]:
        print('   >', l[:100])
