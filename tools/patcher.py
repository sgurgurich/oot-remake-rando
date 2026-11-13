"""Write a romfs mod that changes what item locations contain.

    py tools/patcher.py <plan.json> <out_dir>

plan.json maps a location's placement Hash (the same in child and adult maps) to
the actor it should give, e.g. {"16757992849254467386": "Item_Hookshot"}. How the
item is written depends on the placement:
  chests, pots, crates, ...  Dynamic.Drop__DropActor
  Business Scrubs            Dynamic.ScrubBusiness_ShopItemActorName0
  Gold Skulltulas            Dynamic.Drop__DropActor (added; overrides the token drop table)
  Heart Pieces/Containers    the placement's Gyaml (the object itself is swapped)

Output is <out_dir>/romfs/..., the layout emulators use for romfs mods. The
resource size table is only included if a changed map outgrew its entry.
"""
import sys, os, json, glob, zstandard
sys.path.insert(0, os.path.dirname(__file__))
import zs, byml, rstb

ROM = os.path.join(os.path.dirname(__file__), '..', 'work', 'raw', '131072', 'romfs')

# Which Dynamic field holds the item for each kind of location.
ITEM_FIELDS = ('Drop__DropActor', 'ScrubBusiness_ShopItemActorName0')
FREESTANDING = ('Obj_Heart_Piece', 'Obj_Heart_Container')


def set_item(a, actor):
    """Write `actor` into placement `a`. Returns (description of old value, ok)."""
    g = a.get('Gyaml')
    dyn = a.get('Dynamic')
    field = next((f for f in ITEM_FIELDS if f in (dyn or {})), None)
    if field:
        old = dyn[field]; dyn[field] = actor
        return old, True
    if g == 'Enemy_Skulltula_Gold':
        if dyn is None:
            dyn = a['Dynamic'] = {}
        dyn['Drop__DropActor'] = actor
        return 'token', True
    if g in FREESTANDING or (g.startswith('Shop_') and 'ShopItemIndex' in (dyn or {})):
        a['Gyaml'] = actor   # freestanding pickups and shop shelf items: swap the object itself
        return g, True
    return None, False


def apply(plan, out_dir, rom=ROM, log=print):
    def rel(p):
        return os.path.relpath(p, rom).replace(os.sep, '/')
    plan = {int(k): v for k, v in plan.items()}
    found = {h: 0 for h in plan}
    changed = {}
    for path in sorted(glob.glob(os.path.join(rom, 'Banc', '*', '*.bcett.byml.zs'))):
        root = byml.load(zs.decompress(rom, path))
        hit = False
        for a in root.get('Actors') or []:
            h = a.get('Hash')
            if h not in plan: continue
            g = a.get('Gyaml')
            old, ok = set_item(a, plan[h])
            if not ok:
                log('skip %d in %s: no item field' % (h, rel(path))); continue
            log('%s  %s: %s -> %s' % (rel(path), g, old, plan[h]))
            found[h] += 1; hit = True
        if hit: changed[rel(path)] = byml.dump(root)

    missing = [h for h, n in found.items() if n == 0]
    if missing: raise SystemExit('locations not found: %s' % missing)

    dicts = zs.dicts(rom)
    cctx = zstandard.ZstdCompressor(level=19, dict_data=dicts['bcett.byml.zsdic'], write_checksum=False)
    table_path = glob.glob(os.path.join(rom, 'System', 'Resource', '*.rsizetable.zs'))[0]
    table = rstb.Rstb(zstandard.ZstdDecompressor().decompress(open(table_path, 'rb').read(), max_output_size=1 << 28))
    table_dirty = False
    for r, data in changed.items():
        dst = os.path.join(out_dir, 'romfs', r)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        blob = cctx.compress(data)
        # sanity: the game's dictionary must read it back
        assert zstandard.ZstdDecompressor(dict_data=dicts['bcett.byml.zsdic']).decompress(blob) == data
        open(dst, 'wb').write(blob)
        key = r[:-3]
        need = rstb.bcett_size(len(data))
        if need > (table.get(key) or 0):
            log('size table: %s %s -> %d' % (key, table.get(key), need))
            table.set(key, need); table_dirty = True
    if table_dirty:
        dst = os.path.join(out_dir, 'romfs', rel(table_path))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(zstandard.ZstdCompressor(level=19).compress(table.dump()))
    return sorted(changed) + ([rel(table_path)] if table_dirty else [])


if __name__ == '__main__':
    plan = json.load(open(sys.argv[1]))
    plan = {k: v for k, v in plan.items() if not k.startswith('_')}
    for f in apply(plan, sys.argv[2]):
        print('wrote', f)
