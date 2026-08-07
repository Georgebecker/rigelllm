import struct

GGUF_VALUE_TYPE = [
    "UINT8", "INT8", "UINT16", "INT16", "UINT32", "INT32",
    "FLOAT32", "BOOL", "STRING", "ARRAY", "UINT64", "INT64", "FLOAT64"
]

def read_value(f, val_type):
    if val_type == 0: return struct.unpack('<B', f.read(1))[0]
    elif val_type == 1: return struct.unpack('<b', f.read(1))[0]
    elif val_type == 2: return struct.unpack('<H', f.read(2))[0]
    elif val_type == 3: return struct.unpack('<h', f.read(2))[0]
    elif val_type == 4: return struct.unpack('<I', f.read(4))[0]
    elif val_type == 5: return struct.unpack('<i', f.read(4))[0]
    elif val_type == 6: return struct.unpack('<f', f.read(4))[0]
    elif val_type == 7: return struct.unpack('<?', f.read(1))[0]
    elif val_type == 8:
        strlen = struct.unpack('<Q', f.read(8))[0]
        return f.read(strlen).decode('utf-8')
    elif val_type == 9:
        arr_type = struct.unpack('<I', f.read(4))[0]
        arr_len = struct.unpack('<Q', f.read(8))[0]
        items = []
        for _ in range(arr_len):
            val = read_value(f, arr_type)
            items.append(val)
        return items
    elif val_type == 10: return struct.unpack('<Q', f.read(8))[0]
    elif val_type == 11: return struct.unpack('<q', f.read(8))[0]
    elif val_type == 12: return struct.unpack('<d', f.read(8))[0]
    else: return None

def read_gguf_header(path):
    with open(path, 'rb') as f:
        magic = f.read(4)
        version = struct.unpack('<I', f.read(4))[0]
        tensor_count = struct.unpack('<Q', f.read(8))[0]
        metadata_count = struct.unpack('<Q', f.read(8))[0]
        metas = {}
        for i in range(metadata_count):
            key_len = struct.unpack('<Q', f.read(8))[0]
            key = f.read(key_len).decode('utf-8')
            val_type = struct.unpack('<I', f.read(4))[0]
            metas[key] = (val_type, read_value(f, val_type))
    return version, tensor_count, metas

# Compara os dois arquivos
files = ['gguf/rigelslm_Q4_K.gguf', 'gguf/rigelslm_Q4_K_M.gguf', 'gguf/rigelslm_F16.gguf']
for path in files:
    try:
        ver, tc, metas = read_gguf_header(path)
        print(f'\n=== {path} ===')
        print(f'Versao: {ver}, Tensores: {tc}, Metadados: {len(metas)}')
        # Mostra diferenças
        for k, (vt, v) in metas.items():
            vname = GGUF_VALUE_TYPE[vt] if vt < len(GGUF_VALUE_TYPE) else f'T{vt}'
            if vt == 9:  # array
                print(f'  {vname} {k}: {len(v)} items')
            elif vt == 8:  # string
                print(f'  {vname} {k}: {str(v)[:100]}')
            else:
                print(f'  {vname} {k}: {v}')
    except FileNotFoundError:
        print(f'\n=== {path} === [NAO ENCONTRADO]')
