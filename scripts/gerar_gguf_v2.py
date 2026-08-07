"""Gera GGUF v2 manualmente para compatibilidade máxima com Ollama."""
import struct
import json
import torch
import numpy as np
import tempfile
import os
import hashlib
from tokenizers import Tokenizer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importa sem os prints problemáticos
import warnings
warnings.filterwarnings('ignore')

from converter_para_gguf import mapear_tensores, NUM_LAYERS, EMBED_DIM, VOCAB_SIZE, SEQ_LEN

print("Carregando modelo...")
sd = torch.load('modelo/modelo_melhor.pt', map_location='cpu', mmap=True)
tensores = mapear_tensores(sd)
print(f"Tensores mapeados: {len(tensores)}")

print("Carregando tokenizer...")
tokenizer = Tokenizer.from_file('tokenizer/tokenizer.json')

# Extrai merges
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    temp_path = f.name
tokenizer.save(temp_path)
with open(temp_path, 'r', encoding='utf-8') as f:
    tok_data = json.load(f)
os.unlink(temp_path)
merges_list = tok_data['model']['merges']
merges_str = '\n'.join(f'{a} {b}' for a, b in merges_list)

vocab = tokenizer.get_vocab()
sorted_vocab = sorted(vocab.items(), key=lambda x: x[1])
tokens = [token for token, _ in sorted_vocab]

print(f"Tokens: {len(tokens)}, Merges: {len(merges_list)}")
print("Escrevendo GGUF v2...")

output = 'gguf/rigelslm_v2.gguf'
f = open(output, 'wb')

# Header
f.write(b'GGUF')
f.write(struct.pack('<I', 2))  # GGUF v2
f.write(struct.pack('<Q', len(tensores)))  # tensor count
f.write(struct.pack('<Q', 9))  # metadata count - minimal

# Metadados simples (apenas essenciais)
# 1. general.architecture = llama
key = b'general.architecture'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 8))  # STRING type
val = b'llama'
f.write(struct.pack('<Q', len(val)))
f.write(val)

# 2. llama.vocab_size = VOCAB_SIZE
key = b'llama.vocab_size'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 4))  # UINT32
f.write(struct.pack('<I', VOCAB_SIZE))

# 3. llama.embedding_length = EMBED_DIM
key = b'llama.embedding_length'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 4))
f.write(struct.pack('<I', EMBED_DIM))

# 4. llama.block_count = NUM_LAYERS
key = b'llama.block_count'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 4))
f.write(struct.pack('<I', NUM_LAYERS))

# 5. llama.feed_forward_length = 2048
key = b'llama.feed_forward_length'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 4))
f.write(struct.pack('<I', 2048))

# 6. llama.attention.head_count = 8
key = b'llama.attention.head_count'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 4))
f.write(struct.pack('<I', 8))

# 7. general.name
key = b'general.name'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 8))
val = b'RigelSLM'
f.write(struct.pack('<Q', len(val)))
f.write(val)

# 8. tokenizer.ggml.model
key = b'tokenizer.ggml.model'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 8))
val = b'gpt2'
f.write(struct.pack('<Q', len(val)))
f.write(val)

# 9. tokenizer.ggml.merges (como string)
key = b'tokenizer.ggml.merges'
f.write(struct.pack('<Q', len(key)))
f.write(key)
f.write(struct.pack('<I', 8))  # STRING
val = merges_str.encode('utf-8')
f.write(struct.pack('<Q', len(val)))
f.write(val)

# Tensors info
for nome, tensor in tensores.items():
    name_bytes = nome.encode('utf-8')
    f.write(struct.pack('<Q', len(name_bytes)))
    f.write(name_bytes)
    # Dimensões: n_dims (uint32), followed by dimensions (uint64 each)
    shape = tensor.shape
    f.write(struct.pack('<I', len(shape)))
    for d in reversed(shape):  # GGUF usa ordem reversa (numpy/fortran)
        f.write(struct.pack('<Q', d))
    # Tipo (GGML_TYPE_F32 = 0)
    f.write(struct.pack('<I', 0))

# Tensor data (all tensors consecutively)
for nome, tensor in tensores.items():
    f.write(tensor.tobytes())

f.close()
size = Path(output).stat().st_size
h = hashlib.sha256()
with open(output, 'rb') as f:
    h.update(f.read())
print(f"GGUF v2 criado: {size/1024/1024:.2f} MB")
print(f"SHA256: {h.hexdigest()}")
print(f"Tensores: {len(tensores)}")
