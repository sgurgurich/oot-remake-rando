"""BYML reader (little-endian 'YB' and big-endian 'BY', v2-v7) and writer.

Values map to Python types, with wrappers where the BYML type is ambiguous so a
load -> dump round trip keeps every node's type:
  str -> 0xA0 string        bytes -> 0xA1 binary       Bin(data, align) -> 0xA2
  list -> 0xC0 array        dict  -> 0xC1 dictionary   HashMap32/HashMap64 -> 0x20/0x21
  bool -> 0xD0              int   -> 0xD1 s32          float -> 0xD2 f32
  U32 -> 0xD3   I64 -> 0xD4   U64 -> 0xD5   F64 -> 0xD6   None -> 0xFF
"""
import struct


class U32(int): pass
class I64(int): pass
class U64(int): pass
class F64(float): pass
class HashMap32(dict): pass
class HashMap64(dict): pass


class Bin:
    def __init__(self, data, align):
        self.data, self.align = data, align

    def __eq__(self, o):
        return isinstance(o, Bin) and (self.data, self.align) == (o.data, o.align)

    def __hash__(self):
        return hash((self.data, self.align))

    def __repr__(self):
        return 'Bin(%d bytes, align=%d)' % (len(self.data), self.align)


# ---------------------------------------------------------------- reader

class Byml:
    def __init__(self, data):
        self.d = data
        assert data[:2] in (b'YB', b'BY'), data[:2]
        self.big = data[:2] == b'BY'
        e = self.e = '>' if self.big else '<'
        self.version, kt, st, root = struct.unpack_from(e + 'HIII', data, 2)
        self.keys = self._strtab(kt) if kt else []
        self.strs = self._strtab(st) if st else []
        self.root = self._node(data[root], root) if root else None

    def _u24(self, off):
        return int.from_bytes(self.d[off:off + 3], 'big' if self.big else 'little')

    def _strtab(self, off):
        n = self._u24(off + 1)
        offs = struct.unpack_from(self.e + '%dI' % (n + 1), self.d, off + 4)
        return [self.d[off + offs[i]:off + offs[i + 1] - 1].decode('utf-8') for i in range(n)]

    def _val(self, t, raw):
        d = self.d
        if t == 0xA0: return self.strs[raw]
        if t == 0xA1:
            n = struct.unpack_from(self.e + 'I', d, raw)[0]
            return bytes(d[raw + 4:raw + 4 + n])
        if t == 0xA2:
            n, align = struct.unpack_from(self.e + 'II', d, raw)
            return Bin(bytes(d[raw + 8:raw + 8 + n]), align)
        if t in (0xC0, 0xC1, 0x20, 0x21): return self._node(t, raw)
        if t == 0xD0: return bool(raw)
        if t == 0xD1: return raw - (1 << 32) if raw & 0x80000000 else raw
        if t == 0xD2: return struct.unpack('<f', struct.pack('<I', raw))[0]
        if t == 0xD3: return U32(raw)
        if t == 0xD4: return I64(struct.unpack_from(self.e + 'q', d, raw)[0])
        if t == 0xD5: return U64(struct.unpack_from(self.e + 'Q', d, raw)[0])
        if t == 0xD6: return F64(struct.unpack_from(self.e + 'd', d, raw)[0])
        if t == 0xFF: return None
        raise ValueError('unknown value type %#x' % t)

    def _node(self, t, off):
        d = self.d
        e = self.e
        assert d[off] == t, (hex(d[off]), hex(t), hex(off))
        n = self._u24(off + 1)
        if t == 0xC0:
            types = d[off + 4:off + 4 + n]
            voff = off + 4 + ((n + 3) & ~3)
            vals = struct.unpack_from(e + '%dI' % n, d, voff)
            return [self._val(types[i], vals[i]) for i in range(n)]
        if t == 0xC1:
            out = {}
            for i in range(n):
                ent = off + 4 + 8 * i
                v = struct.unpack_from(e + 'I', d, ent + 4)[0]
                out[self.keys[self._u24(ent)]] = self._val(d[ent + 3], v)
            return out
        if t in (0x20, 0x21):
            hs = 4 if t == 0x20 else 8
            es = hs + 4
            types = d[off + 4 + es * n:off + 4 + es * n + n]
            out = HashMap32() if t == 0x20 else HashMap64()
            for i in range(n):
                e = off + 4 + es * i
                h = struct.unpack_from(self.e + ('I' if hs == 4 else 'Q'), d, e)[0]
                out[h] = self._val(types[i], struct.unpack_from(self.e + 'I', d, e + hs)[0])
            return out
        raise ValueError('unknown node type %#x at %#x' % (t, off))


def load(data):
    return Byml(data).root


# ---------------------------------------------------------------- writer

def _type(v):
    if isinstance(v, bool): return 0xD0
    if isinstance(v, str): return 0xA0
    if isinstance(v, bytes): return 0xA1
    if isinstance(v, Bin): return 0xA2
    if isinstance(v, HashMap32): return 0x20
    if isinstance(v, HashMap64): return 0x21
    if isinstance(v, dict): return 0xC1
    if isinstance(v, list): return 0xC0
    if isinstance(v, U32): return 0xD3
    if isinstance(v, I64): return 0xD4
    if isinstance(v, U64): return 0xD5
    if isinstance(v, int): return 0xD1
    if isinstance(v, F64): return 0xD6
    if isinstance(v, float): return 0xD2
    if v is None: return 0xFF
    raise TypeError('cannot encode %r' % type(v))


def _collect(v, keys, strs):
    if isinstance(v, str):
        strs.add(v)
    elif isinstance(v, (HashMap32, HashMap64)):
        for x in v.values(): _collect(x, keys, strs)
    elif isinstance(v, dict):
        for k, x in v.items():
            keys.add(k); _collect(x, keys, strs)
    elif isinstance(v, list):
        for x in v: _collect(x, keys, strs)


def _hdr(t, n, big):
    """Node header: type byte, then a 24-bit count in the file's byte order."""
    return bytes([t]) + n.to_bytes(3, 'big' if big else 'little')


def _strtab(strings, big=False):
    """0xC2 string table node: header, offsets (n+1), NUL-terminated strings."""
    e_ = '>' if big else '<'
    enc = [s.encode('utf-8') for s in strings]
    n = len(enc)
    out = bytearray(_hdr(0xC2, n, big))
    pos = 4 + 4 * (n + 1)
    offs = []
    for e in enc:
        offs.append(pos); pos += len(e) + 1
    offs.append(pos)
    out += struct.pack(e_ + '%dI' % (n + 1), *offs)
    for e in enc: out += e + b'\0'
    return out


def _key(v, memo):
    """Hashable identity of a value including its BYML type (floats by bit pattern)."""
    t = _type(v)
    if t in (0xC0, 0xC1, 0x20, 0x21):
        k = memo.get(id(v))
        if k is None:
            if t == 0xC0: body = tuple(_key(x, memo) for x in v)
            elif t == 0xC1: body = tuple(sorted((k2, _key(x, memo)) for k2, x in v.items()))
            else: body = tuple(sorted((h, _key(x, memo)) for h, x in v.items()))
            k = memo[id(v)] = (t, body)
        return k
    if t == 0xD2: return (t, struct.pack('<f', v))
    if t == 0xD6: return (t, struct.pack('<d', v))
    if t == 0xA2: return (t, v.data, v.align)
    return (t, v)


def dump(root, version=7, dedup=True, big=False):
    """BYML bytes for root. big=True writes the big-endian 'BY' form (GameDataList uses it)."""
    e = '>' if big else '<'
    keys, strs = set(), set()
    _collect(root, keys, strs)
    key_list = sorted(keys, key=lambda s: s.encode('utf-8'))
    str_list = sorted(strs, key=lambda s: s.encode('utf-8'))
    key_idx = {k: i for i, k in enumerate(key_list)}
    str_idx = {s: i for i, s in enumerate(str_list)}

    buf = bytearray(16)

    def align(a):
        buf.extend(b'\0' * (-len(buf) % a))

    kt = st = 0
    if key_list:
        kt = len(buf); buf += _strtab(key_list, big); align(4)
    if str_list:
        st = len(buf); buf += _strtab(str_list, big); align(4)

    # Containers are written breadth-first; each placeholder slot is patched once
    # the child node's offset is known. 64-bit and binary payloads are written
    # right after the container that references them. Like Nintendo's writer,
    # identical containers and payloads are stored once and shared.
    memo, written = {}, {}

    def write_container(v):
        align(4)
        off = len(buf)
        t = _type(v)
        if t == 0xC0:
            n = len(v)
            buf.extend(_hdr(t, n, big))
            buf.extend(bytes(_type(x) for x in v)); align(4)
            items = list(v)
        elif t == 0xC1:
            n = len(v)
            buf.extend(_hdr(t, n, big))
            items = sorted(v.items(), key=lambda kv: key_idx[kv[0]])
        else:
            n = len(v)
            buf.extend(_hdr(t, n, big))
            items = sorted(v.items())
        slots = []
        for i, item in enumerate(items):
            if t == 0xC0:
                x = item
                slot = len(buf); buf.extend(b'\0\0\0\0')
            elif t == 0xC1:
                k, x = item
                buf.extend(key_idx[k].to_bytes(3, 'big' if big else 'little') + bytes([_type(x)]))
                slot = len(buf); buf.extend(b'\0\0\0\0')
            else:
                k, x = item
                buf.extend(struct.pack(e + ('I' if t == 0x20 else 'Q'), k))
                slot = len(buf); buf.extend(b'\0\0\0\0')
            slots.append((slot, x))
        if t in (0x20, 0x21):
            buf.extend(bytes(_type(x) for _, x in slots)); align(4)
        pending = []
        for slot, x in slots:
            xt = _type(x)
            if xt in (0xC0, 0xC1, 0x20, 0x21):
                pending.append((slot, x)); continue
            if xt in (0xD4, 0xD5, 0xD6, 0xA1, 0xA2):
                k = _key(x, memo) if dedup else None
                if k in written:
                    struct.pack_into(e + 'I', buf, slot, written[k]); continue
                if xt == 0xA2:
                    align(4); p = len(buf)
                    buf.extend(struct.pack(e + 'II', len(x.data), x.align)); buf.extend(x.data)
                elif xt == 0xA1:
                    align(4); p = len(buf)
                    buf.extend(struct.pack(e + 'I', len(x))); buf.extend(x)
                else:
                    align(4); p = len(buf)  # Nintendo's files use 4-byte alignment here
                    buf.extend(struct.pack(e + {0xD4: 'q', 0xD5: 'Q', 0xD6: 'd'}[xt], x))
                raw = p
                if dedup: written[k] = p
            elif xt == 0xA0: raw = str_idx[x]
            elif xt == 0xD0: raw = int(x)
            elif xt == 0xD1: raw = x & 0xFFFFFFFF
            elif xt == 0xD2: raw = struct.unpack('<I', struct.pack('<f', x))[0]
            elif xt == 0xD3: raw = int(x)
            else: raw = 0
            struct.pack_into(e + 'I', buf, slot, raw)
        return off, pending

    root_off = 0
    if root is not None:
        queue = [(None, root)]
        while queue:
            nxt = []
            for slot, v in queue:
                k = _key(v, memo) if dedup else None
                if k in written:
                    struct.pack_into(e + 'I', buf, slot, written[k]); continue
                off, pending = write_container(v)
                if dedup: written[k] = off
                if slot is None: root_off = off
                else: struct.pack_into(e + 'I', buf, slot, off)
                nxt.extend(pending)
            queue = nxt
    align(4)
    struct.pack_into(e + '2sHIII', buf, 0, b'BY' if big else b'YB', version, kt, st, root_off)
    return bytes(buf)
