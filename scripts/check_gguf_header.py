import struct

with open('gguf/rigelslm_F16.gguf', 'rb') as f:
    data = f.read(24)

magic = data[0:4].decode('utf-8')
version = struct.unpack('<I', data[4:8])[0]
tensor_count = struct.unpack('<Q', data[8:16])[0]
metadata_count = struct.unpack('<Q', data[16:24])[0]

print(f'Magic: {magic}')
print(f'Versao: {version}')
print(f'Tensores: {tensor_count}')
print(f'Metadados: {metadata_count}')
