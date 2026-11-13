"""Reader for the .nup container (Switch 2 cartridge dump).

Layout (reverse-engineered, all little-endian):
  0x000  'NUP\x01', u16 0x80 (header size), u16 1, u32 toc_offset (0x80)
  0x010  u64 data_region_start-ish, 32-byte hash, u64 first file data offset ...
  0x080  TOC: 'TOC\x01', u32 ver(2), u32 dir_count, u32 0,
         u64 file_count, u64 strtab_off (rel. to TOC), u64 strtab_size
  0x0B0  title records, 0x40 bytes each (title id u64, ..., meta off u64, meta size u64)
  0x130  dir_count dir entries, 24 bytes: name_off, name_len, first_child, child_count, 0, 0
  then   file_count file entries, 80 bytes:
           name_off u32, name_len u32, size u64, offset u64 (absolute),
           stored_size u64, sha256[32], 16 bytes extra
  then   u32 child list (child slot -> node id; ids >= dir_count are files)
  then   string table (names, not NUL terminated)
"""
import struct, sys, os, hashlib

DIR_FMT = '<IIII8x'
FILE_FMT = '<IIQQQ32s16s'

class Nup:
    def __init__(self, path):
        self.path = path
        f = self.f = open(path, 'rb')
        hdr = f.read(0x80)
        assert hdr[:4] == b'NUP\x01', hdr[:4]
        self.toc_off = struct.unpack_from('<I', hdr, 8)[0]
        f.seek(self.toc_off)
        toc = f.read(0x30)
        assert toc[:4] == b'TOC\x01'
        _, ver, self.dir_count, _, self.file_count, stroff, strsize = struct.unpack_from('<4sIIIQQQ', toc)
        self.str_off = self.toc_off + stroff
        f.seek(self.str_off); self.strtab = f.read(strsize)
        self.dirs_off = 0x130
        f.seek(self.dirs_off)
        raw = f.read(self.dir_count * 24)
        self.dirs = [struct.unpack_from(DIR_FMT, raw, i * 24) for i in range(self.dir_count)]
        self.files_off = self.dirs_off + self.dir_count * 24
        f.seek(self.files_off)
        raw = f.read(self.file_count * 80)
        self.files = [struct.unpack_from(FILE_FMT, raw, i * 80) for i in range(self.file_count)]
        self.child_off = self.files_off + self.file_count * 80
        nchild = (self.str_off - self.child_off) // 4
        f.seek(self.child_off)
        self.children = struct.unpack('<%dI' % nchild, f.read(nchild * 4))

    def name(self, off, ln):
        return self.strtab[off:off + ln].decode('utf-8', 'replace')

    def walk(self):
        """Yield (path, file_entry) for every file."""
        return self._walk(False)

    def walk_ids(self):
        """Yield (path, index into self.files) for every file."""
        for path, fe in self._walk(True):
            yield path, fe

    def _walk(self, ids):
        referenced = set()
        for d in self.dirs:
            referenced.update(self.children[d[2]:d[2] + d[3]])
        roots = [i for i in range(self.dir_count) if i not in referenced]
        stack = [(r, '') for r in reversed(roots)]
        while stack:
            node, prefix = stack.pop()
            if node < self.dir_count:
                d = self.dirs[node]
                p = prefix + self.name(d[0], d[1]) + '/'
                for c in reversed(self.children[d[2]:d[2] + d[3]]):
                    stack.append((c, p))
            else:
                i = node - self.dir_count
                fe = self.files[i]
                yield prefix + self.name(fe[0], fe[1]), (i if ids else fe)

    def read(self, fe):
        self.f.seek(fe[3])
        return self.f.read(fe[4])

if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    n = Nup(path)
    if cmd == 'info':
        print('dirs', n.dir_count, 'files', n.file_count, 'children', len(n.children))
        print('child list @', hex(n.child_off), 'strtab @', hex(n.str_off))
    elif cmd == 'list':
        for p, fe in n.walk():
            flag = '' if fe[2] == fe[4] else ' stored=%d' % fe[4]
            print('%12d %12x %s%s %s' % (fe[2], fe[3], p, flag, fe[6].hex() if any(fe[6]) else ''))
    elif cmd == 'extract':
        out, pattern = sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ''
        for p, fe in n.walk():
            if pattern in p:
                dst = os.path.join(out, p)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                data = n.read(fe)
                ok = hashlib.sha256(data).digest() == fe[5]
                open(dst, 'wb').write(data)
                print(('OK  ' if ok else 'BAD ') + p)
