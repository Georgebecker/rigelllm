"""Testa merges como string única em vez de array."""
import gguf
import json
import torch
import numpy as np
import tempfile
import os
from tokenizers import Tokenizer
from pathlib import Path

# Adiciona raiz ao path para importar mapear_tensores
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from converter_para_gguf import mapear_tensores, NUM_LAYERS, VOCAB_SIZE, EMBED_DIM, SEQ_LEN

tokenizer = Tokenizer.from_file('tokenizer/tokenizer.json')

# Extrai merges como string (separados por newline)
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    temp_path = f.name
tokenizer.save(temp_path)
with open(temp_path, 'r', encoding='utf-8') as f:
    tok_data = json.load(f)
merges_list = tok_data['model']['merges']
merges_str = '\n'.join(f'{a} {b}' for a, b in merges_list)
os.unlink(temp_path)
print(f'Merges: {len(merges_list)} como string de {len(merges_str)} chars')

# Carrega modelo completo
sd = torch.load('modelo/modelo_melhor.pt', map_location='cpu')

# Mapeia tensores
tensores = mapear_tensores(sd)
print(f'Tensores: {len(tensores)}')

writer = gguf.GGUFWriter(path='gguf/rigelslm_str_merges.gguf', arch='llama')

# Metadados
writer.add_uint32('llama.context_length', SEQ_LEN)
writer.add_uint32('llama.embedding_length', EMBED_DIM)
writer.add_uint32('llama.block_count', NUM_LAYERS)
writer.add_uint32('llama.feed_forward_length', 2048)
writer.add_uint32('llama.attention.head_count', 8)
writer.add_uint32('llama.attention.head_count_kv', 8)
writer.add_float32('llama.attention.layer_norm_rms_epsilon', 1e-5)
writer.add_uint32('llama.rope.dimension_count', EMBED_DIM // 8)
writer.add_uint32('llama.vocab_size', VOCAB_SIZE)
writer.add_uint32('general.vocab_size', VOCAB_SIZE)
writer.add_uint32('general.file_type', 0)
writer.add_string('general.name', 'RigelSLM')
writer.add_string('general.description', 'RigelSLM - Small Language Model para Português Brasileiro')

# Tokenizer - modelo gpt2
writer.add_string('tokenizer.ggml.model', 'gpt2')

# Em vez de ARRAY de strings, serializa merges como STRING única
writer.add_string('tokenizer.ggml.merges', merges_str)

# Tokens como array (Ollama aceita)
vocab = tokenizer.get_vocab()
sorted_vocab = sorted(vocab.items(), key=lambda x: x[1])
tokens = [token for token, _ in sorted_vocab]
writer.add_array('tokenizer.ggml.tokens', tokens)
writer.add_array('tokenizer.ggml.scores', [0.0] * len(tokens))
writer.add_array('tokenizer.ggml.token_type', [0] * len(tokens))

writer.add_bool('tokenizer.ggml.add_space_prefix', True)
writer.add_bool('tokenizer.ggml.add_bos_token', True)
writer.add_bool('tokenizer.ggml.remove_extra_whitespace', False)
writer.add_uint32('tokenizer.ggml.pad_token_id', 0)
writer.add_uint32('tokenizer.ggml.unk_token_id', 1)
writer.add_uint32('tokenizer.ggml.bos_token_id', 2)
writer.add_uint32('tokenizer.ggml.eos_token_id', 3)
writer.add_uint32('tokenizer.ggml.sep_token_id', 4)

# Tensores
for nome, tensor in tensores.items():
    writer.add_tensor(nome, tensor, raw_dtype=gguf.GGMLQuantizationType.F32)

writer.write_header_to_file()
writer.write_kv_data_to_file()
writer.write_tensors_to_file()
writer.close()
size = Path('gguf/rigelslm_str_merges.gguf').stat().st_size
print(f'GGUF criado: {size / 1024 / 1024:.2f} MB')
