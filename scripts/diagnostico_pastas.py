#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnóstico: pastas canarim*/curtos*/datasets2* no cache TXT vs disco real vs JSONL explodidos."""
import json
import pathlib

cache = json.load(open(r'd:\Projetos\rigelllm\logs\estrutura_cache\estrutura_txt.json', encoding='utf-8'))
res = cache.get('resultado', [])
base = pathlib.Path(r'd:\Projetos\rigelllm\dados\processed')
ger = pathlib.Path(r'd:\Projetos\rigelllm\dados\gerados\jsonl')

print('=== pastas canarim*/curtos*/datasets2* no CACHE ===')
alvo = []
for p in res:
    n = p.get('nome', '')
    if n.startswith(('canarim', 'curtos', 'datasets2')):
        alvo.append(n)
        print(f'  {n}: cache={p.get("arquivos")} cap={p.get("cap_atingido")}')

print()
print('=== contagem REAL no disco ===')
for n in sorted(alvo):
    pth = base / n
    if pth.exists():
        q = sum(1 for _ in pth.rglob('*.txt'))
        print(f'  {n}: real={q}')
    else:
        print(f'  {n}: NAO EXISTE no disco')

print()
print('=== JSONL explodidos em dados/gerados/jsonl ===')
if ger.exists():
    for d in sorted(ger.iterdir()):
        if d.is_dir():
            print(f'  {d.name}')
