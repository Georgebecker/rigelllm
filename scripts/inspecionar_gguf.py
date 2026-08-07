#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Inspeciona um arquivo GGUF manualmente (sem depender da lib gguf, que na
versao 0.19.0 tem bug de leitura de arrays). Mostra a tabela de tokens,
merges e token_type reais gravados no arquivo.

Uso: python scripts/inspecionar_gguf.py gguf/rigelslm_f16.gguf
"""
import sys
import struct

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def read_string(buf, off):
    ln = struct.unpack('<Q', buf[off:off+8])[0]
    s = buf[off+8:off+8+ln].decode('utf-8', errors='replace')
    return s, off + 8 + ln

# Tipos GGUF
# 0=UINT8 1=INT8 2=UINT16 3=INT16 4=UINT32 5=INT32 6=FLOAT32 7=BOOL
# 8=STRING 9=ARRAY 10=UINT64 11=INT64 12=FLOAT64
TAM = {0:1, 1:1, 2:2, 3:2, 4:4, 5:4, 6:4, 7:1, 10:8, 11:8, 12:8}
NOME = {0:'UINT8',1:'INT8',2:'UINT16',3:'INT16',4:'UINT32',5:'INT32',6:'FLOAT32',
        7:'BOOL',8:'STRING',9:'ARRAY',10:'UINT64',11:'INT64',12:'FLOAT64'}

def main(path, amostra=12):
    data = open(path, 'rb').read()
    if data[:4] != b'GGUF':
        print('Nao e GGUF'); return
    version, tensor_count, kv_count = struct.unpack('<IQQ', data[4:24])
    print(f'GGUF v{version} | tensores: {tensor_count} | kv: {kv_count}')
    off = 24
    tokens = None
    merges = None
    token_type = None
    for _ in range(kv_count):
        k, off = read_string(data, off)
        vtype = struct.unpack('<I', data[off:off+4])[0]; off += 4
        if vtype == 9:  # ARRAY
            st = struct.unpack('<I', data[off:off+4])[0]; off += 4
            n = struct.unpack('<Q', data[off:off+8])[0]; off += 8
            if st == 8:  # array de strings
                itens = []
                for _i in range(n):
                    s, off = read_string(data, off)
                    itens.append(s)
                if k == 'tokenizer.ggml.tokens':
                    tokens = itens
                elif k == 'tokenizer.ggml.merges':
                    merges = itens
            else:
                itens = []
                tam = TAM.get(st)
                for _i in range(n):
                    raw = data[off:off+tam]
                    val = int.from_bytes(raw, 'little', signed=(st in (1,3,5,11)))
                    itens.append(val)
                    off += tam
                if k == 'tokenizer.ggml.token_type':
                    token_type = itens
        elif vtype == 8:  # STRING
            s, off = read_string(data, off)
            if 'token' in k.lower() or 'eos' in k.lower() or 'bos' in k.lower():
                print(f'  {k} = {s!r}')
        else:
            tam = TAM.get(vtype)
            if tam:
                off += tam
    print()
    if tokens is not None:
        print(f'TOKENS: {len(tokens)}')
        for i in range(min(amostra, len(tokens))):
            print(f'  {i:5d} {tokens[i]!r}')
        print('  ...')
        for i in range(max(0, len(tokens)-5), len(tokens)):
            print(f'  {i:5d} {tokens[i]!r}')
    if token_type is not None:
        print(f'TOKEN_TYPE: {len(token_type)} | primeiros 8: {token_type[:8]}')
    if merges is not None:
        print(f'MERGES: {len(merges)} | primeiros 3: {merges[:3]}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Uso: python scripts/inspecionar_gguf.py <arquivo.gguf>')
        sys.exit(1)
    main(sys.argv[1])
