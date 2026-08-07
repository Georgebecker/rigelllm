"""Verifica os tipos reais dos tensores nos GGUFs."""
import gguf
import numpy as np

for path in ["gguf/rigelslm_Q4_K.gguf", "gguf/rigelslm_Q4_K_M.gguf"]:
    reader = gguf.GUFFReader(path)
    nome = path.split("/")[-1]
    print(f"\n=== {nome} ===")
    
    # Primeiro tensor
    t = reader.tensors[0]
    print(f"Tensor 0: nome={t.name}")
    print(f"  shape={t.shape}")
    print(f"  data tipo={type(t.data)}")
    print(f"  data len={len(t.data)}")
    print(f"  data[:16]={t.data[:16].hex()}")
    
    # Tenta diferentes interpretações
    data_f32 = np.frombuffer(t.data, dtype=np.float32)
    data_f16 = np.frombuffer(t.data, dtype=np.float16)
    print(f"  como f32: primeiros={data_f32[:5]}")
    print(f"  como f16: primeiros={data_f16[:5]}")
