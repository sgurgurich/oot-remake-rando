"""RESTBL resource size table (System/Resource/ResourceSizeTable.*.rsizetable.zs).

Layout: 'RESTBL', u32 version (1), u32 name_len (160), u32 crc_count, u32 name_count,
then crc_count x (u32 crc32(path), u32 size) sorted by crc, then name_count x
(char[name_len] path, u32 size) for paths whose CRCs collide.
Paths are romfs-relative without the trailing '.zs'.

For .bcett.byml maps the stored size is align32(decompressed_size) + 264
(checked against all Kokiri Forest maps).
"""
import struct, zlib


class Rstb:
    def __init__(self, data):
        assert data[:6] == b'RESTBL', data[:6]
        self.version, self.name_len, ncrc, nname = struct.unpack_from('<IIII', data, 6)
        off = 22
        self.crc = dict(struct.unpack_from('<II', data, off + 8 * i) for i in range(ncrc))
        off += 8 * ncrc
        self.names = {}
        for _ in range(nname):
            n = data[off:off + self.name_len].split(b'\0')[0].decode()
            self.names[n] = struct.unpack_from('<I', data, off + self.name_len)[0]
            off += self.name_len + 4
        assert off == len(data)

    def get(self, path):
        if path in self.names: return self.names[path]
        return self.crc.get(zlib.crc32(path.encode()))

    def set(self, path, size):
        if path in self.names: self.names[path] = size
        else: self.crc[zlib.crc32(path.encode())] = size

    def dump(self):
        out = bytearray(b'RESTBL')
        out += struct.pack('<IIII', self.version, self.name_len, len(self.crc), len(self.names))
        for c in sorted(self.crc): out += struct.pack('<II', c, self.crc[c])
        for n in sorted(self.names):
            out += n.encode().ljust(self.name_len, b'\0') + struct.pack('<I', self.names[n])
        return bytes(out)


def bcett_size(decompressed_len):
    return ((decompressed_len + 31) & ~31) + 264
