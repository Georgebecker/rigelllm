import struct

GGUF_VALUE_TYPE = [
    "UINT8", "INT8", "UINT16", "INT16", "UINT32", "INT32",
    "FLOAT32", "BOOL", "STRING", "ARRAY", "UINT64", "INT64", "FLOAT64"
]

def read_value(f, val_type):
    if val_type == 0: return struct.unpack('<B', f.read(1))[0], "UINT8"
    elif val_type == 1: return struct.unpack('<b', f.read(1))[0], "INT8"
    elif val_type == 2: return struct.unpack('<H', f.read(2))[0], "UINT16"
    elif val_type == 3: return struct.unpack('<h', f.read(2))[0], "INT16"
    elif val_type == 4: return struct.unpack('<I', f.read(4))[0], "UINT32"
    elif val_type == 5: return struct.unpack('<i', f.read(4))[0], "INT32"
    elif val_type == 6: return struct.unpack('<f', f.read(4))[0], "FLOAT32"
    elif val_type == 7: return struct.unpack('<?', f.read(1))[0], "BOOL"
    elif val_type == 8:
        strlen = struct.unpack('<Q', f.read(8))[0]
        return f.read(strlen).decode('utf-8'), "STRING"
    elif val_type == 9:
        arr_type = struct.unpack('<I', f.read(4))[0]
        arr_len = struct.unpack('<Q', f.read(8))[0]
        items = []
        for _ in range(arr_len):
            val, _ = read_value(f, arr_type)
            items.append(val)
        return items, f"ARRAY[{GGUF_VALUE_TYPE[arr_type]}]"
    elif val_type == 10: return struct.unpack('<Q', f.read(8))[0], "UINT64"
    elif val_type == 11: return struct.unpack('<q', f.read(8))[0], "INT64"
    elif val_type == 12: return struct.unpack('<d', f.read(8))[0], "FLOAT64"
    else: return None, f"UNKNOWN({val_type})"

with open('gguf/rigelslm_F16.gguf', 'rb') as f:
    # Header
    magic = f.read(4)
    version = struct.unpack('<I', f.read(4))[0]
    tensor_count = struct.unpack('<Q', f.read(8))[0]
    metadata_count = struct.unpack('<Q', f.read(8))[0]

    print(f'GGUF v{version}, {tensor_count} tensores, {metadata_count} metadados\n')

    # Metadata KV pairs
    print("=== METADADOS ===")
    for i in range(metadata_count):
        # Key
        key_len = struct.unpack('<Q', f.read(8))[0]
        key = f.read(key_len).decode('utf-8')
        # Value type
        val_type = struct.unpack('<I', f.read(4))[0]
        type_name = GGUF_VALUE_TYPE[val_type] if val_type < len(GGUF_VALUE_TYPE) else f"UNKNOWN({val_type})"
        # Value
        val, _ = read_value(f, val_type)
        if isinstance(val, list):
            val_str = f'[{len(val)} items]'
            if len(val) > 0:
                val_str += f' first: {str(val[0])[:80]}'
        else:
            val_str = str(val)[:200]
        print(f'  [{type_name}] {key} = {val_str}')

print("\n=== FIM (tensores nao lidos) ===")

print("\n=== TENSORES (primeiros 5) ===")
for i, tensor in enumerate(reader.tensors):
    if i < 5:
        print(f'  {tensor.name}: shape={tensor.shape} dtype={tensor.dtype}')
print(f'  ... total: {len(reader.tensors)} tensores')
