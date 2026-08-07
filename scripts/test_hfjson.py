"""Testa GGUF com tokenizer serializado como hf_json."""
import gguf
import json
import torch
import numpy as np
from tokenizers import Tokenizer
from pathlib import Path

# Carrega tokenizer
tokenizer = Tokenizer.from_file('tokenizer/tokenizer.json')

# Salva como JSON
tok_json_path = 'tokenizer/tokenizer_hf.json'
tokenizer.save(tok_json_path)
with open(tok_json_path, 'r', encoding='utf-8') as f:
    tok_data = json.load(f)

# Carrega modelo
sd = torch.load('modelo/modelo_melhor.pt', map_location='cpu')
emb = sd['embedding.weight'].numpy().astype(np.float32)
while emb.ndim > 2:
    emb = emb.squeeze()

# Escreve GGUF usando hf_json em vez de arrays individuais
writer = gguf.GGUFWriter(path='gguf/test_hfjson.gguf', arch='llama')

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

# Usa hf_json em vez de arrays
writer.add_string('tokenizer.ggml.model', 'gpt2')
writer.add_string('tokenizer.ggml.hf_json', json.dumps(tok_data))
writer.add_bool('tokenizer.ggml.add_space_prefix', True)
writer.add_bool('tokenizer.ggml.add_bos_token', True)
writer.add_bool('tokenizer.ggml.remove_extra_whitespace', False)
writer.add_uint32('tokenizer.ggml.pad_token_id', 0)
writer.add_uint32('tokenizer.ggml.unk_token_id', 1)
writer.add_uint32('tokenizer.ggml.bos_token_id', 2)
writer.add_uint32('tokenizer.ggml.eos_token_id', 3)
writer.add_uint32('tokenizer.ggml.sep_token_id', 4)

# Tensor
writer.add_tensor('token_embd.weight', emb.T, raw_dtype=gguf.GGMLQuantizationType.F32)

writer.write_header_to_file()
writer.write_kv_data_to_file()
writer.write_tensors_to_file()
writer.close()
print('GGUF com hf_json criado!')
print(f'Tamanho: {Path("gguf/test_hfjson.gguf").stat().st_size / 1024 / 1024:.2f} MB')
