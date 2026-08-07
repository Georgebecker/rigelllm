"""Verifica como extrair merges do tokenizer."""
from tokenizers import Tokenizer
import json
import os

t = Tokenizer.from_file('tokenizer/tokenizer.json')

print("=== Atributos do tokenizer ===")
for attr in dir(t):
    if not attr.startswith('_'):
        print(f'  {attr}')

print("\n=== Model ===")
if hasattr(t, 'model'):
    print(f'Tipo: {type(t.model)}')
    if hasattr(t.model, 'merges'):
        merges = t.model.merges
        print(f'Merges no model: {len(merges)}')
        if merges:
            print(f'Primeiro: {merges[0]}')
    print('Atributos do model:')
    for attr in dir(t.model):
        if not attr.startswith('_'):
            print(f'  {attr}')

print("\n=== JSON ===")
t.save('tokenizer/temp_check.json')
with open('tokenizer/temp_check.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print(f'Chaves principais: {list(data.keys())}')
if 'model' in data:
    print(f'Chaves do model: {list(data["model"].keys())}')
    if 'merges' in data['model']:
        merges = data['model']['merges']
        print(f'Merges encontrados: {len(merges)}')
        print(f'Primeiro: {merges[0]}')
os.unlink('tokenizer/temp_check.json')
