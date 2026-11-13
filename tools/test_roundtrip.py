"""Round-trip every Banc map: load -> dump -> load must give identical, identically-typed values."""
import sys, os, glob, struct, time
sys.path.insert(0, os.path.dirname(__file__))
import zs, byml

def same(a, b, path='root'):
    if type(a) is not type(b): return '%s: type %s != %s' % (path, type(a).__name__, type(b).__name__)
    if isinstance(a, dict):
        if list(a.keys()) != list(b.keys()) and set(a) != set(b): return '%s: keys differ' % path
        for k in a:
            r = same(a[k], b[k], '%s.%s' % (path, k))
            if r: return r
    elif isinstance(a, list):
        if len(a) != len(b): return '%s: len %d != %d' % (path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            r = same(x, y, '%s[%d]' % (path, i))
            if r: return r
    elif isinstance(a, float):
        fmt = '<d' if isinstance(a, byml.F64) else '<f'
        if struct.pack(fmt, a) != struct.pack(fmt, b): return '%s: %r != %r' % (path, a, b)
    elif a != b: return '%s: %r != %r' % (path, a, b)
    return None

if __name__ == '__main__':
    ROM = sys.argv[1]
    files = sorted(glob.glob(os.path.join(ROM, 'Banc', '*', '*.bcett.byml.zs')))
    if len(sys.argv) > 2: files = [f for f in files if sys.argv[2] in f]
    fails = 0; t0 = time.time(); grow = 0
    for p in files:
        orig = zs.decompress(ROM, p)
        a = byml.load(orig)
        out = byml.dump(a)
        b = byml.load(out)
        r = same(a, b)
        grow = max(grow, len(out) - len(orig))
        if r or len(out) != len(orig):
            print('%s %s orig=%d new=%d %s' % ('FAIL' if r else 'size', os.path.relpath(p, ROM), len(orig), len(out), r or ''))
        fails += bool(r)
    print('%d files, %d failures, max growth %d bytes, %.0fs' % (len(files), fails, grow, time.time() - t0))
