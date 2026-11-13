"""Minimal MSBT reader: returns {label: text} with control tags rendered as {tag}."""
import struct

def load(data):
    assert data[:8] == b'MsgStdBn', data[:8]
    bom = data[8:10]
    e = '<' if bom == b'\xff\xfe' else '>'
    enc = data[0x0C]
    nsec = struct.unpack_from(e + 'H', data, 0x0E)[0]
    off = 0x20
    sec = {}
    for _ in range(nsec):
        magic = data[off:off + 4]; size = struct.unpack_from(e + 'I', data, off + 4)[0]
        sec[magic] = data[off + 16:off + 16 + size]
        off = (off + 16 + size + 15) & ~15
    labels = {}
    lbl = sec[b'LBL1']
    n = struct.unpack_from(e + 'I', lbl, 0)[0]
    for i in range(n):
        cnt, o = struct.unpack_from(e + 'II', lbl, 4 + 8 * i)
        for _ in range(cnt):
            ln = lbl[o]; name = lbl[o + 1:o + 1 + ln].decode(); idx = struct.unpack_from(e + 'I', lbl, o + 1 + ln)[0]
            labels[idx] = name; o += 1 + ln + 4
    txt = sec[b'TXT2']
    n = struct.unpack_from(e + 'I', txt, 0)[0]
    offs = list(struct.unpack_from(e + '%dI' % n, txt, 4)) + [len(txt)]
    out = {}
    for i in range(n):
        raw = txt[offs[i]:offs[i + 1]]
        s, j = [], 0
        cw = 1 if enc == 0 else 2  # encoding byte: 0 = UTF-8, 1 = UTF-16
        while j + cw <= len(raw):
            ch = raw[j] if cw == 1 else struct.unpack_from(e + 'H', raw, j)[0]
            if ch == 0: break
            if ch == 0x0E:  # tag: group, type, size, params
                g, t, sz = struct.unpack_from(e + 'HHH', raw, j + cw)
                s.append('{%d.%d}' % (g, t)); j += cw + 6 + sz; continue
            if ch == 0x0F:
                s.append('{/}'); j += cw + 4; continue
            if cw == 1:
                k = j + 1
                while k < len(raw) and raw[k] not in (0, 0x0E, 0x0F): k += 1
                s.append(raw[j:k].decode('utf-8', 'replace')); j = k; continue
            s.append(chr(ch)); j += 2
        out[labels.get(i, str(i))] = ''.join(s)
    return out
