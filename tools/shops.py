"""Build data/shops.json: every shop shelf slot and the price file of every shop item.

    py tools/shops.py        (needs Banc/ and Pack/Actor/Shop_*.pack.zs extracted into work/raw)

Shop stock is placed objects: a Shop_<item> actor with Dynamic.ShopItemIndex (its shelf slot).
Shuffling swaps which Shop_ actor sits in a slot (the placement Gyaml). Prices are not per
slot but per item: each Shop_<item> actor pack has a PriceParam (BuyingPrice), referenced
from its GameParameterTable. Only actors that already have a Shop_ version can be sold, so
shops can only shuffle shop items among themselves.
"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dump, zs, byml

ROM = dump.ROM
OUT = os.path.join(HERE, '..', 'data', 'shops.json')
SHOP_NAMES = {  # map + slot range -> readable shop name is not stored in the data; name shops by area
    'KokiriForest': 'Kokiri Shop', 'Market': 'Market', 'KakarikoVillage': 'Kakariko Village',
    'GoronCity': 'Goron Shop', 'ZoraDomain': 'Zora Shop',
}
# Equipment the logic assumes is bought where the original game sells it.
KEEP = ('Shop_Armor_', 'Shop_Weapon_Shield_', 'Shop_Mask_', 'Shop_Sword_')


def _resolve(files, ref):
    """'?A/B.bgyml' or 'Work/A/B.gyml' -> the matching file name inside the pack."""
    name = ref.lstrip('?')
    if name.startswith('Work/'):
        name = name[5:]
    if name.endswith('.gyml'):
        name = name[:-5] + '.bgyml'
    return name if name in files else None


def _component(files, name, key, depth=0):
    """Look up Components[key] in a bgyml, following $parent like the engine does."""
    if not name or depth > 8: return None
    root = byml.load(files[name])
    comp = (root.get('Components') or {}).get(key)
    if comp: return comp
    parent = root.get('$parent')
    return _component(files, _resolve(files, parent), key, depth + 1) if parent else None


def price_file(pack_rel, actor):
    files = zs.sarc(zs.decompress(ROM, os.path.join(ROM, pack_rel)))
    param = 'Actor/%s.engine__actor__ActorParam.bgyml' % actor
    if param not in files: return None, None
    table = _component(files, param, 'GameParameterTableRef')
    table = table and _resolve(files, table)
    price = table and _component(files, table, 'PriceParam')
    name = price and _resolve(files, price)
    if not name: return None, None
    return name, int(byml.load(files[name])['BuyingPrice'])


def main():
    slots = {}
    for p in sorted(glob.glob(os.path.join(ROM, 'Banc', '*', '*.bcett.byml.zs'))):
        rel = os.path.relpath(p, ROM).replace(os.sep, '/')
        area = rel.split('/')[1]
        if area == 'DreamWorld': continue
        age = 'child' if '_Child_' in rel else 'adult' if '_Adult_' in rel else 'any'
        for a in dump.load(rel).get('Actors') or []:
            g = a.get('Gyaml', ''); dyn = a.get('Dynamic') or {}
            if not g.startswith('Shop_') or 'ShopItemIndex' not in dyn: continue
            s = slots.setdefault(a['Hash'], {'id': str(a['Hash']), 'area': area, 'shop': SHOP_NAMES.get(area, area),
                                             'index': dyn['ShopItemIndex'], 'vanilla': g, 'ages': [], 'files': []})
            if age not in s['ages']: s['ages'].append(age)
            if rel not in s['files']: s['files'].append(rel)
    prices = {}
    for actor in sorted({s['vanilla'] for s in slots.values()}):
        rel = 'Pack/Actor/%s.pack.zs' % actor
        if not os.path.exists(os.path.join(ROM, rel)):
            raise SystemExit('extract %s first' % rel)
        name, price = price_file(rel, actor)
        if name: prices[actor] = {'pack': rel, 'file': name, 'price': price, 'keep': actor.startswith(KEEP)}
    import inventory
    _, pouch = inventory.text()
    names = {}
    for actor in sorted({s['vanilla'] for s in slots.values()}):
        stem = actor[len('Shop_'):]
        n = (inventory.item_name(actor, pouch) or inventory.item_name('Item_' + stem.rsplit('_0', 1)[0], pouch)
             or inventory.item_name(stem.replace('Armor_', 'Armor_Adult_', 1), pouch))
        names[actor] = n or stem.replace('_', ' ')
    data = {'slots': list(slots.values()), 'prices': prices, 'names': names}
    json.dump(data, open(OUT, 'w', encoding='utf-8'), indent=1)
    print('%d shop slots, %d items with prices -> %s' % (len(slots), len(prices), OUT))
    for a, v in prices.items(): print('  %-32s %5d%s' % (a, v['price'], '  (kept: equipment)' if v['keep'] else ''))


if __name__ == '__main__':
    main()
