import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))
import zs, byml
ROM = os.path.join(os.path.dirname(__file__), '..', 'work', 'raw', '131072', 'romfs')
def load(rel):
    p = os.path.join(ROM, rel)
    data = zs.decompress(ROM, p) if p.endswith('.zs') else open(p, 'rb').read()
    return byml.load(data)
if __name__ == '__main__':
    obj = load(sys.argv[1])
    json.dump(obj, sys.stdout, indent=1, ensure_ascii=False, default=lambda b: b.hex() if isinstance(b, bytes) else str(b))
