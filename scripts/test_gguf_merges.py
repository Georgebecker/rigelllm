"""Testa se o llama-cli aceita GGUF com merges."""
import gguf
import json
import os
import tempfile
import numpy as np
from tokenizers import Tokenizer
from pathlib import Path

# Carrega tokenizer
tokenizer = Tokenizer.from_file('tokenizer/tokenizer.json')

# Extrai merges
merges = []
if hasattr(tokenizer, 'model') and hasattr(tokenizer.model, 'merges'):
    merges = [f'{a} {b}' for a, b in tokenizer.model.merges]
    print(f'Encontrados {len(merges)} merges no tokenizer.model.merges')
else:
    print('Procurando merges de outra forma...')
    # Salva tokenizer como JSON com encoding utf-8
    temp_path = 'tokenizer/tokenizer_temp.json'
    tokenizer.save(temp_path)
    with open(temp_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'model' in data and 'merges' in data['model']:
        merges = data['model']['merges']
        print(f'Extraidos {len(merges)} merges do JSON')
    os.unlink(temp_path)

print(f'Merges encontrados: {len(merges)}')
if merges:
    print(f'Primeiro merge: {merges[0]}')

# Vocab
vocab = tokenizer.get_vocab()
sorted_vocab = sorted(vocab.items(), key=lambda x: x[1])
tokens = [token for token, _ in sorted_vocab]
scores = [0.0] * len(tokens)
print(f'Tokens: {len(tokens)}')

# Gera GGUF com merges
import torch
sd = torch.load('modelo/modelo_melhor.pt', map_location='cpu')
emb = sd['embedding.weight'].numpy().astype(np.float32)
while emb.ndim > 2:
    emb = emb.squeeze()

writer = gguf.GGUFWriter(path='gguf/test_merges.gguf', arch='llama')

writer.add_uint32('llama.context_length', 512)
writer.add_uint32('llama.embedding_length', 512)
writer.add_uint32('llama.block_count', 8)
writer.add_uint32('llama.feed_forward_length', 2048)
writer.add_uint32('llama.attention.head_count', 8)
writer.add_uint32('llama.attention.head_count_kv', 8)
writer.add_float32('llama.attention.layer_norm_rms_epsilon', 1e-5)
writer.add_uint32('llama.rope.dimension_count', 64)
writer.add_uint32('llama.vocab_size', 23830)
writer.add_uint32('general.vocab_size', 23830)
writer.add_uint32('general.file_type', 0)

# Tokenizer COM merges
writer.add_string('tokenizer.ggml.model', 'gpt2')
writer.add_array('tokenizer.ggml.tokens', tokens)
writer.add_array('tokenizer.ggml.scores', scores)
writer.add_array('tokenizer.ggml.token_type', [0] * len(tokens))
writer.add_array('tokenizer.ggml.merges', merges)
writer.add_bool('tokenizer.ggml.add_space_prefix', True)
writer.add_bool('tokenizer.ggml.add_bos_token', True)
writer.add_bool('tokenizer.ggml.remove_extra_whitespace', False)
writer.add_uint32('tokenizer.ggml.pad_token_id', 0)
writer.add_uint32('tokenizer.ggml.unk_token_id', 1)
writer.add_uint32('tokenizer.ggml.bos_token_id', 2)
writer.add_uint32('tokenizer.ggml.eos_token_id', 3)
writer.add_uint32('tokenizer.ggml.sep_token_id', 4)

# Apenas embedding (para teste rápido)
writer.add_tensor('token_embd.weight', emb.T, raw_dtype=gguf.GGMLQuantizationType.F32)

writer.write_header_to_file()
writer.write_kv_data_to_file()
writer.write_tensors_to_file()
writer.close()
print('GGUF de teste criado: gguf/test_merges.gguf')
print(f'Tamanho: {Path("gguf/test_merges.gguf").stat().st_size / 1024 / 1024:.2f} MB')
