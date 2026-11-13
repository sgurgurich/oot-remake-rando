"""Change the starting value of GameData flags in place (GameDataList.Product.110.byml.zs).

A new save starts with every flag at its DefaultValue. This changes Bool defaults by
rewriting the 4-byte value slot of 'DefaultValue' inside the original big-endian BYML, so
no other byte of the file moves (re-serialising would reorder containers).

Layout used: root dict -> 'Data' dict -> 'Bool' array -> one dict per flag with 'Hash' (u32)
and 'DefaultValue' (bool). Dict entries are 8 bytes: 24-bit key index + type byte, then a u32
value (inline for bools and u32s). Big-endian files store the key index as a big-endian 24-bit
number before the type byte.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import byml
from hashes import murmur3

PATH = 'GameData/GameDataList.Product.110.byml.zs'


class _Doc:
    def __init__(self, data):
        self.d = data
        self.r = byml.Byml(data)           # for the key table and endianness
        self.e = self.r.e
        self.keys = {k: i for i, k in enumerate(self.r.keys)}
        self.root = struct.unpack_from(self.e + 'I', data, 0x0C)[0]

    def dict_entries(self, off):
        """[(key, type, value_slot_offset)] for the dict node at off."""
        d = self.d
        assert d[off] == 0xC1
        n = self.r._u24(off + 1)
        out = []
        for i in range(n):
            ent = off + 4 + 8 * i
            out.append((self.r.keys[self.r._u24(ent)], d[ent + 3], ent + 4))
        return out

    def child(self, off, key):
        for k, t, slot in self.dict_entries(off):
            if k == key:
                return t, struct.unpack_from(self.e + 'I', self.d, slot)[0], slot
        raise KeyError(key)

    def array(self, off):
        d = self.d
        assert d[off] == 0xC0
        n = self.r._u24(off + 1)
        voff = off + 4 + ((n + 3) & ~3)
        return [(d[off + 4 + i], struct.unpack_from(self.e + 'I', d, voff + 4 * i)[0]) for i in range(n)]


def bool_slots(data):
    """{flag hash: offset of its DefaultValue u32} for every Bool flag."""
    doc = _Doc(data)
    _, data_off, _ = doc.child(doc.root, 'Data')
    _, bools_off, _ = doc.child(data_off, 'Bool')
    out = {}
    for t, off in doc.array(bools_off):
        if t != 0xC1: continue
        ent = {k: (ty, slot) for k, ty, slot in doc.dict_entries(off)}
        if 'Hash' in ent and 'DefaultValue' in ent and ent['DefaultValue'][0] == 0xD0:
            h = struct.unpack_from(doc.e + 'I', data, ent['Hash'][1])[0]
            out[h] = ent['DefaultValue'][1]
    return out, doc.e


def set_bool_defaults(data, values):
    """data with Bool DefaultValues changed. values: {flag name: bool}. Unknown names fail."""
    slots, e = bool_slots(data)
    out = bytearray(data)
    for name, v in values.items():
        h = murmur3(name)
        if h not in slots:
            raise KeyError('no Bool flag %s' % name)
        struct.pack_into(e + 'I', out, slots[h], 1 if v else 0)
    return bytes(out)


def bool_default(data, name):
    slots, e = bool_slots(data)
    return bool(struct.unpack_from(e + 'I', data, slots[murmur3(name)])[0])
