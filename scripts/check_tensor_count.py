"""Verifica número de tensores no GGUF."""
import gguf

path = 'gguf/rigelslm_final3.gguf'
reader = gguf.GGUFReader(path)
print(f'Tensores: {len(reader.tensors)}')
for t in reader.tensors:
    print(f'  {t.name}: {t.shape}')
