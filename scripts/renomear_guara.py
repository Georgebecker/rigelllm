#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Renomeia dados/processed/jsonl/adalbertojunior_Guara -> rigeljsonl_20260802_0136
seguindo a REGRA DE OURO 5 (nomes padrão rigeljsonl_*).

- Renomeia a pasta e os 941 arquivos internos
- Atualiza o registro de treino (modelo/jsonlogs/*.json)
- Apaga o cache de estrutura para regenerar
"""
import json
import pathlib

base = pathlib.Path(r'd:\Projetos\rigelllm\dados\processed\jsonl')
antiga = base / 'adalbertojunior_Guara'
nova = base / 'rigeljsonl_20260802_0136'
prefixo_antigo = 'adalbertojunior_Guara'
prefixo_novo = 'rigeljsonl_20260802_0136'

# 1 + 2) renomeia arquivos internos e a pasta
if antiga.exists():
    n = 0
    for f in list(antiga.glob(prefixo_antigo + '_*.jsonl')):
        novo_nome = prefixo_novo + f.name[len(prefixo_antigo):]
        f.rename(antiga / novo_nome)
        n += 1
    print(f'1) arquivos renomeados: {n}')
    if not nova.exists():
        antiga.rename(nova)
        print(f'2) pasta renomeada: {antiga.name} -> {nova.name}')
else:
    print('0) pasta antiga não existe (já renomeada?)')

# 3) atualiza jsonlogs (registro de treino)
jl = pathlib.Path(r'd:\Projetos\rigelllm\modelo\jsonlogs')
src = jl / (prefixo_antigo + '.json')
if src.exists():
    d = json.loads(src.read_text(encoding='utf-8'))
    d['dataset'] = prefixo_novo
    d['arquivos'] = {(prefixo_novo + k[len(prefixo_antigo):]): v
                     for k, v in d['arquivos'].items()}
    (jl / (prefixo_novo + '.json')).write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    src.unlink()
    qtd = len(d['arquivos'])
    print(f'3) jsonlogs atualizado -> {prefixo_novo}.json ({qtd} registros)')
else:
    print('3) jsonlogs antigo não encontrado')

# 4) apaga cache para regenerar
cache = pathlib.Path(r'd:\Projetos\rigelllm\logs\estrutura_cache\estrutura_jsonl.json')
if cache.exists():
    cache.unlink()
    print('4) cache estrutura_jsonl.json apagado (regenera no próximo acesso)')
