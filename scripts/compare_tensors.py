"""Compara tensores entre GGUF antigo (funciona) e novo (não funciona)."""
import gguf
import numpy as np

old_path = "gguf/rigelslm_Q4_K.gguf"
new_path = "gguf/rigelslm_Q4_K_M.gguf"

old_reader = gguf.GGUFReader(old_path)
new_reader = gguf.GGUFReader(new_path)

old_tensors = {t.name: t for t in old_reader.tensors}
new_tensors = {t.name: t for t in new_reader.tensors}

print(f"GGUF antigo: {len(old_tensors)} tensores")
print(f"GGUF novo:   {len(new_tensors)} tensores")

# Compara shapes e dados
diferencas = 0
for name in old_tensors:
    if name not in new_tensors:
        print(f"  ❌ Tensor {name} só existe no antigo")
        diferencas += 1
        continue
    
    old_t = old_tensors[name]
    new_t = new_tensors[name]
    
    old_data = np.frombuffer(old_t.data, dtype=np.float32)
    new_data = np.frombuffer(new_t.data, dtype=np.float32)
    
    shape_ok = np.array_equal(old_t.shape, new_t.shape)
    size_ok = len(old_data) == len(new_data)
    
    if not bool(shape_ok) or not bool(size_ok):
        print(f"  ❌ {name}: old_shape={old_t.shape} new_shape={new_t.shape} old_size={len(old_data)} new_size={len(new_data)}")
        diferencas += 1
    else:
        # Verifica se os dados são iguais (aproximadamente)
        diff = np.max(np.abs(old_data - new_data))
        if diff > 1e-5:
            print(f"  ⚠️  {name}: shapes iguais, mas dados diferentes (max_diff={diff:.6f})")
            diferencas += 1

for name in new_tensors:
    if name not in old_tensors:
        print(f"  ❌ Tensor {name} só existe no novo")
        diferencas += 1

if diferencas == 0:
    print("\n✅ Tensores IDÊNTICOS entre os dois GGUF!")
else:
    print(f"\n⚠️  {diferencas} diferenças encontradas")
