"""Decode the game's UI icon textures (BNTX, Switch 2 'Ounc' platform) to PNG.

    py tools/bntx.py <file.bntx[.zs]> <out.png>

Only what the item icons use is supported: one 2D texture, ASTC (any block size), tiled with
the Tegra block-linear layout (64-byte x 8-row GOBs, block height from the texture info).
BRTI fields used (offsets from 'BRTI'): 0x1C format (high byte = type, 0x2d.. = ASTC 4x4 ...),
0x24 width, 0x28 height, 0x34 log2 block height (in GOBs); texture data follows BRTD + 0x10.
"""
import os, struct, sys, zlib

# NX/Ounc texture format high byte -> ASTC block size
ASTC = {0x2d: (4, 4), 0x2e: (5, 4), 0x2f: (5, 5), 0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5), 0x33: (8, 6),
        0x34: (8, 8), 0x35: (10, 5), 0x36: (10, 6), 0x37: (10, 8), 0x38: (10, 10), 0x39: (12, 10), 0x3a: (12, 12)}


def info(d):
    if d[:4] != b'BNTX':
        raise ValueError('not a BNTX file')
    i = d.find(b'BRTI')
    fmt, = struct.unpack_from('<I', d, i + 0x1C)
    w, h = struct.unpack_from('<II', d, i + 0x24)
    bh_log2, = struct.unpack_from('<I', d, i + 0x34)
    size, = struct.unpack_from('<I', d, i + 0x50)
    data = d.find(b'BRTD') + 0x10
    return {'format': fmt, 'width': w, 'height': h, 'block_height': 1 << bh_log2, 'size': size, 'data': data}


def deswizzle(src, width_bytes, rows, block_height):
    """Block-linear -> linear for 16-byte texel blocks (ASTC). width_bytes is a row of blocks in
    bytes, rows is the number of block rows. A GOB is 64 bytes x 8 rows = 512 bytes; a block is
    block_height GOBs stacked vertically; blocks run left to right, then down.

    Inside a GOB, this platform orders the 16-byte elements by the address bits
    (from bit 4 up) y0, y1, x4, y2, x5 (x in bytes, y in rows). The Switch 1 (Tegra X1)
    order is y0, x4, y1, y2, x5; using it here leaves every other block row in the wrong place.
    The order was found by decoding an icon with all 120 bit orders and keeping the smooth one.
    """
    gobs_x = (width_bytes + 63) // 64
    block_bytes = 512 * block_height
    out = bytearray(width_bytes * rows)
    for y in range(rows):
        by, gy = divmod(y, 8 * block_height)
        gob_in_block, yy = divmod(gy, 8)
        ybits = ((yy & 1) << 4) | (((yy >> 1) & 1) << 5) | (((yy >> 2) & 1) << 7)
        row_base = by * gobs_x * block_bytes + gob_in_block * 512
        for x in range(0, width_bytes, 16):
            gx, xx = divmod(x, 64)
            off = row_base + gx * block_bytes + ybits + (((xx >> 4) & 1) << 6) + (((xx >> 5) & 1) << 8)
            out[y * width_bytes + x:y * width_bytes + x + 16] = src[off:off + 16]
    return bytes(out)


def decode(d):
    """(width, height, RGBA bytes) for a single-texture ASTC BNTX."""
    import texture2ddecoder
    t = info(d)
    kind = t['format'] >> 8
    if kind not in ASTC:
        raise ValueError('unsupported texture format %#x' % t['format'])
    bw, bh = ASTC[kind]
    cols, rows = (t['width'] + bw - 1) // bw, (t['height'] + bh - 1) // bh
    linear = deswizzle(d[t['data']:t['data'] + t['size']], cols * 16, rows, t['block_height'])
    bgra = texture2ddecoder.decode_astc(linear, t['width'], t['height'], bw, bh)
    rgba = bytearray(bgra)
    rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
    return t['width'], t['height'], bytes(rgba)


def png(width, height, rgba):
    def chunk(tag, body):
        c = tag + body
        return struct.pack('>I', len(body)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def downscale(width, height, rgba, size):
    """Box-filter shrink to size x size (alpha-weighted), for small tracker icons."""
    out = bytearray(size * size * 4)
    for oy in range(size):
        y0, y1 = oy * height // size, max(oy * height // size + 1, (oy + 1) * height // size)
        for ox in range(size):
            x0, x1 = ox * width // size, max(ox * width // size + 1, (ox + 1) * width // size)
            r = g = b = a = 0
            for y in range(y0, y1):
                row = y * width * 4
                for x in range(x0, x1):
                    i = row + x * 4
                    al = rgba[i + 3]
                    r += rgba[i] * al; g += rgba[i + 1] * al; b += rgba[i + 2] * al; a += al
            n = (y1 - y0) * (x1 - x0)
            j = (oy * size + ox) * 4
            if a:
                out[j:j + 4] = bytes((r // a, g // a, b // a, a // n))
    return size, size, bytes(out)


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    src, dst = sys.argv[1], sys.argv[2]
    raw = open(src, 'rb').read()
    if src.endswith('.zs'):
        import zstandard
        raw = zstandard.ZstdDecompressor().decompress(raw, max_output_size=1 << 28)
    w, h, rgba = decode(raw)
    open(dst, 'wb').write(png(w, h, rgba))
    print('wrote %s (%dx%d)' % (dst, w, h))
