"""Write data/tracker.json: what the item tracker shows and which save flags mean "found".

    py tools/tracker_data.py

Each item is found when its IsGet.<actor> flag is set in the save (the game sets it the
first time the item enters the inventory). Progressive items list their stages in order;
the highest one found is shown. Counters read Int flags. Every flag used here is checked
against GameData/GameDataList, so a typo fails the build instead of silently never lighting.
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dump, inventory
from hashes import murmur3

OUT = os.path.join(HERE, '..', 'data', 'tracker.json')

GROUPS = [
    ('Items', 'var(--gold)', [
        ['Weapon_Range_SlingShot'], ['Item_Boomerang'], ['Item_BombBag_Small', 'Item_BombBag_Medium', 'Item_BombBag_Large'],
        ['Item_Bombchu'], ['Weapon_Range_Bow'], ['Item_Arrow_Fire'], ['Item_Arrow_Ice'], ['Item_Arrow_Light'],
        ['Item_Hookshot', 'Item_Longshot'], ['Item_Hammer'], ['Armor_GlassTruth'], ['Item_MagicBean'],
        ['Item_DinFire'], ['Item_FaroreWind'], ['Item_NayruLove'], ['Item_Ocarina_Fairy', 'Item_Ocarina_Time'],
        {'stages': ['Item_Bottle'], 'count': 'bottles', 'max': 6}, ['Item_DekuStick'], ['Item_DekuNut'],
    ]),
    ('Equipment', 'var(--water)', [
        ['Weapon_Sword_Kokiri'], ['Weapon_Sword_Master'], ['Weapon_Sword_Giant', 'Weapon_Sword_Biggoron'],
        ['Weapon_Shield_Deku'], ['Weapon_Shield_Hylian'], ['Weapon_Shield_Mirror'],
        ['Armor_Adult_Goron'], ['Armor_Adult_Zora'], ['Armor_Adult_HeavyBoot'], ['Armor_Adult_HoverBoot'],
    ]),
    ('Upgrades', 'var(--forest)', [
        ['Armor_Child_Gauntlet_Goron', 'Armor_Adult_Gauntlet_Silver', 'Armor_Adult_Gauntlet_Gold'],
        ['Item_Scale_Silver', 'Item_Scale_Gold'], ['Item_Wallet_Medium', 'Item_Wallet_Large'],
        ['Item_FairyBless_MP', 'Item_FairyBless_MPDouble'], ['Item_FairyBless_DefenseDouble'],
        ['Item_AgonyStone'], ['Item_Token_Gerudo'],
    ]),
    ('Trading', 'var(--spirit)', [
        ['Item_WeirdEgg', 'Item_AlarmCucco', 'Item_ZeldaLetter'],
        ['Armor_Child_Mask_Keaton'], ['Armor_Child_Mask_Skull'], ['Armor_Child_Mask_Spooky'], ['Armor_Child_Mask_Bunny'],
        ['Armor_Child_Mask_Truth'], ['Armor_Child_Mask_Goron'], ['Armor_Child_Mask_Zora'], ['Armor_Child_Mask_Gerudo'],
        ['Item_PocketEgg', 'Item_PocketCucco', 'Item_CojiroCucco', 'Item_OddMushroom', 'Item_OddPowder', 'Item_PoacherSaw',
         'Item_BrokenSword', 'Item_Prescription', 'Item_EyeballFrog', 'Item_EyeDrop', 'Item_ClaimCheck'],
    ]),
    ('Songs', 'var(--shadow)', [
        ['Item_Melody_ZeldaLullaby'], ['Item_Melody_EponaSong'], ['Item_Melody_SariaSong'], ['Item_Melody_SunSong'],
        ['Item_Melody_TimeSong'], ['Item_Melody_StormSong'], ['Item_Melody_ForestMinuet'], ['Item_Melody_FireBolero'],
        ['Item_Melody_WaterSerenade'], ['Item_Melody_SpiritRequiem'], ['Item_Melody_ShadowNocturne'],
        ['Item_Melody_LightPrelude'],
    ]),
    ('Stones & Medallions', 'var(--fire)', [
        ['Item_Stone_Forest'], ['Item_Stone_Fire'], ['Item_Stone_Water'],
        ['Item_Medal_Forest'], ['Item_Medal_Fire'], ['Item_Medal_Water'], ['Item_Medal_Spirit'],
        ['Item_Medal_Shadow'], ['Item_Medal_Light'],
    ]),
]
COUNTERS = [
    ('tokens', 'Gold Skulltula Tokens', 'PouchData.Item_Token_Gold.StockNum', 100),
    ('pieces', 'Pieces of Heart', 'PouchData.Obj_Heart_Piece.StockNum', None),
    ('hearts', 'Heart containers', 'PlayerStatus.MaxLife', None),
]
# Stage colours that hint which part of the game a song or medallion belongs to.
TINT = {
    'Item_Melody_ForestMinuet': '#49c27a', 'Item_Medal_Forest': '#49c27a', 'Item_Stone_Forest': '#49c27a',
    'Item_Melody_FireBolero': '#ef6247', 'Item_Medal_Fire': '#ef6247', 'Item_Stone_Fire': '#ef6247',
    'Item_Melody_WaterSerenade': '#4f9cf0', 'Item_Medal_Water': '#4f9cf0', 'Item_Stone_Water': '#4f9cf0',
    'Item_Melody_ShadowNocturne': '#a874e6', 'Item_Medal_Shadow': '#a874e6',
    'Item_Melody_SpiritRequiem': '#f0973a', 'Item_Medal_Spirit': '#f0973a',
    'Item_Melody_LightPrelude': '#f4d867', 'Item_Medal_Light': '#f4d867',
}


def icon_names():
    """Item icons in the romfs (UI/Tex/Icon/<actor>.bntx.zs), from filelist.txt."""
    out = set()
    for line in open(os.path.join(HERE, '..', 'filelist.txt'), encoding='utf-8'):
        p = line.split()
        if len(p) >= 3 and p[2].startswith('131072/romfs/UI/Tex/Icon/') and p[2].endswith('.bntx.zs'):
            out.add(p[2].rsplit('/', 1)[1][:-8])
    return out


# Drawn icons (no game icon): songs are notes, stones are gems, medallions are discs.
SONG_COLORS = {'Item_Melody_ZeldaLullaby': '#c9a4ff', 'Item_Melody_EponaSong': '#f3a35b', 'Item_Melody_SariaSong': '#6fdc8c',
               'Item_Melody_SunSong': '#ffd75e', 'Item_Melody_TimeSong': '#78b6ff', 'Item_Melody_StormSong': '#a9c2d6'}


def main():
    icons = icon_names()
    gd = dump.load('GameData/GameDataList.Product.110.byml.zs')['Data']
    types = {e['Hash']: t for t, lst in gd.items() for e in lst}
    _, pouch = inventory.text()
    groups = []
    for title, color, items in GROUPS:
        out = []
        for entry in items:
            special = entry if isinstance(entry, dict) else {}
            stages = special.get('stages', entry)
            st = []
            for a in stages:
                flag = 'IsGet.' + a
                h = murmur3(flag)
                if types.get(h) != 'Bool':
                    raise SystemExit('no Bool flag %s' % flag)
                name = inventory.item_name(a, pouch) or a.split('_', 1)[1].replace('_', ' ')
                st.append({'actor': a, 'flag': h, 'name': re.sub(r'\{[^}]*\}', '', name).strip(), 'icon': a in icons})
            first = stages[0]
            drawn = 'note' if 'Melody' in first else 'gem' if 'Stone_' in first else 'medal' if 'Medal_' in first else None
            item = {'key': first, 'stages': st, 'tint': TINT.get(first) or SONG_COLORS.get(first), 'drawn': drawn}
            if special.get('count'):
                item.update(count=special['count'], max=special['max'])
            out.append(item)
        groups.append({'title': title, 'color': color, 'items': out})
    counters = []
    for key, label, flag, total in COUNTERS:
        h = murmur3(flag)
        if types.get(h) != 'Int':
            raise SystemExit('no Int flag %s' % flag)
        counters.append({'key': key, 'label': label, 'flag': h, 'total': total})
    # Inventory slots are String64 flags holding an actor name (the wallet slot holds
    # 'Item_Wallet_Small', the seed bag slot 'Item_BulletBag_Small'). Bottles are counted as the
    # slots holding an Item_Bottle* name. Two String64 flags only echo something recent and
    # are left out: 0x72c4152b follows the last item obtained, 0xfb117672 the last equipment.
    strings = sorted(e['Hash'] for e in gd['String64'])
    json.dump({'groups': groups, 'counters': counters, 'string64': strings, 'not_slots': [0x72c4152b, 0xfb117672]},
              open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('wrote %s: %d items, %d counters' % (OUT, sum(len(g['items']) for g in groups), len(counters)))
    for g in groups:
        print('  %s: %s' % (g['title'], ', '.join(' > '.join(s['name'] for s in i['stages']) for i in g['items'])))


if __name__ == '__main__':
    main()
