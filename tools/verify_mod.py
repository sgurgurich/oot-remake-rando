"""Diff a built mod against the original romfs and print every value that changed."""
import sys, os, glob, zstandard
sys.path.insert(0, os.path.dirname(__file__))
import zs, byml, rstb
from test_roundtrip import same

ROM = os.path.join(os.path.dirname(__file__), '..', 'work', 'raw', '131072', 'romfs')
mod = os.path.join(sys.argv[1], 'romfs')

def diffs(a, b, path=''):
    if type(a) is not type(b) or not isinstance(a, (dict, list)):
        if same(a, b): yield path, a, b
        return
    if isinstance(a, dict):
        for k in set(a) | set(b): yield from diffs(a.get(k), b.get(k), path + '.' + str(k))
    else:
        if len(a) != len(b): yield path + '.len', len(a), len(b); return
        for i, (x, y) in enumerate(zip(a, b)): yield from diffs(x, y, '%s[%d]' % (path, i))

for p in glob.glob(os.path.join(mod, '**', '*'), recursive=True):
    if not os.path.isfile(p): continue
    r = os.path.relpath(p, mod).replace(os.sep, '/')
    if r.endswith('.bcett.byml.zs'):
        a = byml.load(zs.decompress(ROM, os.path.join(ROM, r)))
        raw = open(p, 'rb').read()
        b = byml.load(zstandard.ZstdDecompressor(dict_data=zs.dicts(ROM)['bcett.byml.zsdic']).decompress(raw))
        print('==', r, 'actors', len(a['Actors']), '->', len(b['Actors']))
        for path, x, y in diffs(a, b): print('  ', path, ':', x, '->', y)
    elif r.endswith('.rsizetable.zs'):
        a = rstb.Rstb(zstandard.ZstdDecompressor().decompress(open(os.path.join(ROM, r), 'rb').read(), max_output_size=1 << 28))
        b = rstb.Rstb(zstandard.ZstdDecompressor().decompress(open(p, 'rb').read(), max_output_size=1 << 28))
        print('==', r, 'entries', len(a.crc), '->', len(b.crc))
        for c in set(a.crc) | set(b.crc):
            if a.crc.get(c) != b.crc.get(c): print('   crc %08x: %s -> %s' % (c, a.crc.get(c), b.crc.get(c)))
