"""Write data/romfs_manifest.json: every game file the randomizer reads, with its SHA-256.

    py tools/make_manifest.py

The desktop app and `randomize.py --nup` use it to pull exactly these files from a dump
and to refuse a dump of a different game version.
"""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from patcher import ROM

PREFIX = '131072/romfs/'
EXTRA = ['Pack/ZsDic.pack.zs', 'System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs']

if __name__ == '__main__':
    locs = json.load(open(os.path.join(HERE, '..', 'data', 'locations.json'), encoding='utf-8'))
    sys.path.insert(0, os.path.join(HERE, '..'))
    from randomizer import skips, shops, tracker, world
    rels = sorted({f for l in locs for f in l['files']} | set(EXTRA) | set(skips.needed_files())
                  | set(shops.needed_files()) | set(tracker.needed_files()) | set(world.needed_files()))
    files = {r: hashlib.sha256(open(os.path.join(ROM, r), 'rb').read()).hexdigest() for r in rels}
    out = os.path.join(HERE, '..', 'data', 'romfs_manifest.json')
    json.dump({'prefix': PREFIX, 'files': files}, open(out, 'w', encoding='utf-8'), indent=1)
    print('wrote %s (%d files)' % (out, len(files)))
