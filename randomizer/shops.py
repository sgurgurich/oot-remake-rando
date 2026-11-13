"""Shop options: shuffle shop stock, randomize prices.

Data comes from data/shops.json (tools/shops.py). Stock is shuffled among shop shelf slots by
swapping the placed Shop_ actor (see tools/patcher.py). Prices are per item: the BuyingPrice
in that Shop_ actor's PriceParam, edited inside its actor pack. The edit only changes an
integer, so the BYML, the SARC and the decompressed pack keep their sizes and the resource
size table needs no change.

Tunics, shields and masks always stay where the original game sells them (the logic assumes
they can be bought there), and their prices never go above the original.
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import zstandard
import zs, byml

DATA = os.path.join(HERE, '..', 'data', 'shops.json')
PRICE_MODES = {
    'vanilla': None,
    'random': (0.25, 2.0),   # x original, rounded to 5
    'cheap': (0.1, 0.6),
}
MAX_PRICE = 300              # the dearest consumable in the original shops


def data():
    return json.load(open(DATA, encoding='utf-8'))


def needed_files():
    d = data()
    return sorted({f for s in d['slots'] for f in s['files']} | {p['pack'] for p in d['prices'].values()})


def _rng(seed, what):
    return random.Random('%s/shops/%s' % (seed, what))  # independent of the item placement


def stock(seed, settings):
    """{slot id: Shop_ actor} for the slots whose item changes."""
    if not settings.get('shop_items'): return {}
    d = data()
    keep = {a for a, p in d['prices'].items() if p['keep']}
    free = [s for s in d['slots'] if s['vanilla'] not in keep and not s['vanilla'].startswith(('Shop_Armor_', 'Shop_Weapon_Shield_', 'Shop_Mask_', 'Shop_Sword_'))]
    items = [s['vanilla'] for s in free]
    _rng(seed, 'stock').shuffle(items)
    return {s['id']: it for s, it in zip(free, items) if it != s['vanilla']}


def prices(seed, settings):
    """{Shop_ actor: new price} for items whose price changes."""
    mode = PRICE_MODES.get(settings.get('shop_prices', 'vanilla'))
    if not mode: return {}
    rng = _rng(seed, 'prices')
    out = {}
    for actor, p in sorted(data()['prices'].items()):
        old = p['price']
        if old <= 1: continue                     # free loans (masks) and placeholders stay
        new = int(round(old * rng.uniform(*mode) / 5.0)) * 5
        new = max(5, min(new, MAX_PRICE))
        if p['keep']: new = min(new, old)          # equipment never gets dearer
        if new != old: out[actor] = new
    return out


def _sarc_entries(data):
    """[(name, start, end)] with absolute offsets."""
    assert data[:4] == b'SARC'
    _, _, _, data_off = struct.unpack_from('<HHII', data, 4)
    _, n, _ = struct.unpack_from('<HHI', data, 0x18)
    nodes = [struct.unpack_from('<IIII', data, 0x20 + i * 16) for i in range(n)]
    names_off = 0x20 + n * 16 + 8
    out = []
    for h, attr, s, e in nodes:
        noff = names_off + (attr & 0xFFFF) * 4
        out.append((data[noff:data.index(b'\0', noff)].decode(), data_off + s, data_off + e))
    return out


def price_pack(rom, pack_rel, file_name, price):
    """The pack with its PriceParam BuyingPrice set to `price` (same size as before)."""
    path = os.path.join(rom, pack_rel)
    raw = bytearray(zs.decompress(rom, path))
    start, end = next((s, e) for n, s, e in _sarc_entries(raw) if n == file_name)
    old = bytes(raw[start:end])
    b = byml.Byml(old)
    root = b.root
    root['BuyingPrice'] = int(price)
    new = byml.dump(root, version=b.version)
    if len(new) != len(old):
        raise ValueError('%s: price file changed size' % pack_rel)
    raw[start:end] = new
    d = zs.pick_dict(rom, path)
    blob = zstandard.ZstdCompressor(level=19, dict_data=d, write_checksum=False).compress(bytes(raw))
    assert zstandard.ZstdDecompressor(dict_data=d).decompress(blob) == bytes(raw)
    return blob


def write(rom, out_dir, seed, settings):
    """Write repriced packs under out_dir/romfs; returns their romfs paths and the price table."""
    table = data()['prices']
    new = prices(seed, settings)
    done = []
    for actor, price in sorted(new.items()):
        p = table[actor]
        dst = os.path.join(out_dir, 'romfs', p['pack'])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(price_pack(rom, p['pack'], p['file'], price))
        done.append(p['pack'])
    return done, new
