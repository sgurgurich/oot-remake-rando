"""zstd helpers: ZsDic dictionaries + SARC reader."""
import struct, zstandard, os, sys

def sarc(data):
    assert data[:4] == b'SARC', data[:4]
    hdr_len, bom, size, data_off = struct.unpack_from('<HHII', data, 4)
    assert data[0x14:0x18] == b'SFAT'
    _, n, _ = struct.unpack_from('<HHI', data, 0x18)
    nodes = [struct.unpack_from('<IIII', data, 0x20 + i * 16) for i in range(n)]
    sfnt = 0x20 + n * 16
    names_off = sfnt + 8
    out = {}
    for h, attr, s, e in nodes:
        noff = names_off + (attr & 0xFFFF) * 4
        name = data[noff:data.index(b'\0', noff)].decode()
        out[name] = data[data_off + s:data_off + e]
    return out

_dicts = None
def dicts(romfs):
    global _dicts
    if _dicts is None:
        raw = zstandard.ZstdDecompressor().decompress(open(os.path.join(romfs, 'Pack/ZsDic.pack.zs'), 'rb').read())
        _dicts = {k: zstandard.ZstdCompressionDict(v) for k, v in sarc(raw).items()}
    return _dicts

def pick_dict(romfs, name):
    d = dicts(romfs)
    if name.endswith('.bcett.byml.zs'): return d.get('bcett.byml.zsdic')
    if name.endswith('.pack.zs'): return d.get('pack.zsdic')
    return d.get('zs.zsdic')

def decompress(romfs, path):
    raw = open(path, 'rb').read()
    dd = pick_dict(romfs, path)
    dctx = zstandard.ZstdDecompressor(dict_data=dd) if dd else zstandard.ZstdDecompressor()
    return dctx.decompress(raw, max_output_size=1 << 30)
