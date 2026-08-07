#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
patch_gguf_context.py — Ajusta llama.context_length de um GGUF in-place.

O RigelSLM é treinado com SEQ_LEN=512, então o GGUF grava context_length=512
e o Ollama LIMITA o contexto a esse valor (ignorando num_ctx do pedido),
causando o erro "request (N tokens) exceeds the available context size (512)".
Como a posição é sinusoidal (extrapola bem), subimos para 2048.

Uso:
    python scripts/patch_gguf_context.py <arquivo.gguf> [novo_contexto]

Exemplo:
    python scripts/patch_gguf_context.py gguf/rigelslm_Q4_K_M.gguf 2048
"""
import struct
import sys
from pathlib import Path

GGUF_MAGIC = b"GGUF"
GGUF_TYPE_UINT32 = 4


def patch_context_length(caminho, novo=2048):
    p = Path(caminho)
    dados = bytearray(p.read_bytes())

    if dados[:4] != GGUF_MAGIC:
        print(f"❌ {caminho}: não é um GGUF (magic inválido)")
        return False

    offset = 4
    (versao,) = struct.unpack_from("<I", dados, offset)
    offset += 4
    (_tensor_count,) = struct.unpack_from("<Q", dados, offset)
    offset += 8
    (kv_count,) = struct.unpack_from("<Q", dados, offset)
    offset += 8

    achado = False
    for _ in range(kv_count):
        (tam,) = struct.unpack_from("<Q", dados, offset)
        offset += 8
        chave = bytes(dados[offset:offset + tam]).decode("utf-8", "replace")
        offset += tam
        (vt,) = struct.unpack_from("<I", dados, offset)
        offset += 4

        if chave == "llama.context_length":
            if vt == GGUF_TYPE_UINT32:
                struct.pack_into("<I", dados, offset, novo)
                achado = True
            else:
                print(f"⚠️ {caminho}: llama.context_length é tipo {vt}, não uint32")
                return False

        # pula o valor conforme o tipo
        if vt in (0, 1, 7):            # uint8, int8, bool
            offset += 1
        elif vt in (2, 3, 4, 5, 6):    # uint16, int16, uint32, int32, float32
            offset += 4
        elif vt == 8:                  # string
            (tam,) = struct.unpack_from("<Q", dados, offset)
            offset += 8 + tam
        elif vt in (10, 11, 12):       # uint64, int64, float64
            offset += 8
        elif vt == 9:                  # array
            (at,) = struct.unpack_from("<I", dados, offset)
            offset += 4
            (cont,) = struct.unpack_from("<Q", dados, offset)
            offset += 8
            if at in (0, 1, 7):
                offset += cont
            elif at in (2, 3, 4, 5, 6):
                offset += 4 * cont
            elif at in (10, 11, 12):
                offset += 8 * cont
            elif at == 8:
                for _ in range(cont):
                    (tam,) = struct.unpack_from("<Q", dados, offset)
                    offset += 8 + tam
            else:
                print(f"⚠️ {caminho}: tipo de array desconhecido {at} em '{chave}'")
                return False
        else:
            print(f"⚠️ {caminho}: tipo de valor desconhecido {vt} em '{chave}'")
            return False

    if achado:
        p.write_bytes(dados)
        print(f"✅ {caminho}: llama.context_length -> {novo} (GGUF v{versao})")
        return True
    print(f"⚠️ {caminho}: chave llama.context_length não encontrada")
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    novo = int(sys.argv[2]) if len(sys.argv) > 2 else 2048
    sys.exit(0 if patch_context_length(sys.argv[1], novo) else 1)
