"""Build data/locations.json: one entry per item location, de-duplicated across map variants.

A location is identified by its placement Hash, which is the same in the child and adult
copies of an area. Each entry records which map files contain it (so the patcher knows
what to rewrite), whether it exists for child, adult or both, and naming info taken from
the game's own text (area names) and DungeonParam (developer room labels, in Japanese).

    py tools/inventory.py
"""
import sys, os, glob, json, collections
sys.path.insert(0, os.path.dirname(__file__))
import dump, zs, msbt

ROM = dump.ROM
HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, '..', 'data')

# Locations that should never be shuffled. Reasons are kept in the output.
EXCLUDE_EVENTS = {
    'MiniGame_ChoiceTreasure_OpenMissTreasureBox': 'Treasure Chest Shop game',
    'MiniGame_ChoiceTreasure_OpenHitTreasureBox': 'Treasure Chest Shop game',
    'MiniGame_ChoiceTreasure_OpenClearTreasureBox': 'Treasure Chest Shop game prize (minigame rearranges chests)',
}
EXCLUDE_AREAS = {'DreamWorld': 'Hall of Fallen Foes (boss rush) is outside the main game'}


def is_chest(g):
    return g.startswith('Obj_TBox_') or '_Shop_TBox' in g


# Breakable or liftable objects that always drop the same thing (Drop__DropActor).
POT_FAMILIES = ('Obj_Pot_', 'Obj_BrokenBox_', 'Obj_Plant_Grass_', 'Obj_LiftRock_', 'Obj_Kokiri_Beehive',
                'Obj_Tree_', 'Obj_Gerudo_CowBoneDecoration', 'Enemy_FlyingPot_')
NOT_ITEMS = ('Animal_Insect', 'Obj_Fairy')  # bugs and fairies are creatures, not pickups


def classify(a):
    g = a.get('Gyaml', ''); dyn = a.get('Dynamic') or {}
    if is_chest(g) and 'Drop__DropActor' in dyn: return 'chest', dyn['Drop__DropActor']
    if 'ScrubBusiness_ShopItemActorName0' in dyn: return 'scrub', dyn['ScrubBusiness_ShopItemActorName0']
    if g in ('Obj_Heart_Piece', 'Obj_Heart_Container'): return 'freestanding', g
    if g == 'Enemy_Skulltula_Gold': return 'skulltula', 'Obj_Token_Gold'  # drops it via its drop table
    if g.startswith(POT_FAMILIES) and dyn.get('Drop__DropActor') and dyn['Drop__DropActor'] not in NOT_ITEMS:
        return 'pot', dyn['Drop__DropActor']
    return None, None


def actor_names():
    """Every actor that has a pack in the 2.0 romfs, from filelist.txt (py tools/nup.py list)."""
    names = set()
    for line in open(os.path.join(HERE, '..', 'filelist.txt'), encoding='utf-8'):
        parts = line.split()
        if len(parts) >= 3 and parts[2].startswith('131072/romfs/Pack/Actor/') and parts[2].endswith('.pack.zs'):
            names.add(parts[2].rsplit('/', 1)[1][:-8])
    return names


def item_forms(item, actors):
    """The actor to use for `item` in each kind of location, or None where it cannot go.

    'get' objects (Item_*, TBox_*) play the hold-it-up scene and only work where the game
    hands an item over: chests and scrubs. Pick-ups (Obj_*) lie in the world, so they are
    what pots, Gold Skulltulas and freestanding spots need; chests can hold them too (the
    base game puts Heart Pieces in chests)."""
    stem = item.split('_', 1)[1] if '_' in item else item
    if item.startswith('Obj_'):
        get = next((c for c in ('TBox_' + stem, 'Item_' + stem) if c in actors), item)
        world = item
    elif item.startswith(('TBox_', 'Tbox_', 'Item_')):
        get = item
        world = 'Obj_' + stem if 'Obj_' + stem in actors else None
    else:  # Shop_* stock only makes sense in a shop
        return {'get': None, 'world': None, 'scrub': item}
    return {'get': get, 'world': world, 'scrub': get}


def text():
    files = zs.sarc(zs.decompress(ROM, os.path.join(ROM, 'Mals', 'USen.Product.110.sarc.zs')))
    areas = msbt.load(files['LocationMsg/Location.msbt'])
    pouch = msbt.load(files['ActorMsg/PouchContent.msbt'])
    return areas, pouch


def room_labels():
    out = {}
    for d in dump.load('RSDB/DungeonParam.Product.111.rstbl.byml.zs'):
        out[d['__RowId']] = [r.get('Label', '') for r in d['RoomParam']]
    return out


def item_name(actor, pouch):
    """English name for a pickup actor. Chest pickups use different prefixes than the
    pouch (inventory) entries that carry the text, so try the known spellings."""
    stem = actor.split('_', 1)[1] if '_' in actor else actor
    for cand in (actor, 'Weapon_' + stem, 'Armor_Adult_' + stem, 'Armor_' + stem,
                 'Obj_' + stem, 'Item_' + stem, 'Shop_' + stem):
        n = pouch.get(cand + '_Name')
        if n: return n.replace('{201.13}', '')
    return None


def main():
    areas, pouch = text()
    rooms = room_labels()
    locs = collections.OrderedDict()
    for p in sorted(glob.glob(os.path.join(ROM, 'Banc', '*', '*.bcett.byml.zs'))):
        rel = os.path.relpath(p, ROM).replace(os.sep, '/')
        area = rel.split('/')[1]
        base = os.path.basename(rel)
        age = 'child' if '_Child_' in base else 'adult' if '_Adult_' in base else 'any'
        root = dump.load(rel)
        for a in root.get('Actors') or []:
            kind, item = classify(a)
            if not kind: continue
            h = a['Hash']
            dyn = a.get('Dynamic') or {}
            loc = locs.get(h)
            if loc is None:
                room = dyn.get('DefaultDungeonRoomIndex')
                variant = area + ('_' + age.capitalize() if age != 'any' else '')
                labels = rooms.get(area) or rooms.get(variant) or []
                loc = locs[h] = dict(
                    id=str(h), area=area, area_name=areas.get(area, area), kind=kind,
                    actor=a.get('Gyaml'), vanilla=item, event=dyn.get('GetEventName'),
                    room=room, room_label=labels[room] if room is not None and room < len(labels) else None,
                    pos=[round(x, 1) for x in a.get('Translate', [])], ages=[], files=[])
                reason = EXCLUDE_AREAS.get(area) or EXCLUDE_EVENTS.get(loc['event'])
                if item == 'Obj_MiniGame_SmallKey': reason = 'Treasure Chest Shop game key'
                if reason: loc['exclude'] = reason
            elif loc['vanilla'] != item:
                loc.setdefault('vanilla_by_age', {})[age] = item
            if age not in loc['ages']: loc['ages'].append(age)
            if rel not in loc['files']: loc['files'].append(rel)
    out = list(locs.values())
    os.makedirs(DATA, exist_ok=True)
    json.dump(out, open(os.path.join(DATA, 'locations.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    c = collections.Counter((l['kind'], 'excluded' if 'exclude' in l else 'used') for l in out)
    print('locations:', len(out), dict(c))
    actors = actor_names()
    forms = {l['vanilla']: item_forms(l['vanilla'], actors) for l in out}
    json.dump(dict(sorted(forms.items())), open(os.path.join(DATA, 'item_forms.json'), 'w', encoding='utf-8'), indent=1)
    names = {}
    for l in out:
        for actor in [l['vanilla']] + list((l.get('vanilla_by_age') or {}).values()):
            names[actor] = item_name(actor, pouch)
    json.dump(dict(sorted(names.items())), open(os.path.join(DATA, 'item_names.json'), 'w', encoding='utf-8'),
              indent=1, ensure_ascii=False)
    print('unnamed items:', sorted(k for k, v in names.items() if not v))
    return out


if __name__ == '__main__':
    main()
