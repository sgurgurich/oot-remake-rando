"""Randomizer settings: what gets shuffled and how dungeon items behave.

The same dict is used by randomize.py, the desktop app and the spoiler log. Every
option here is backed by something the patcher can actually change in the game files;
see CATEGORIES[...]['note'] for what is still untested in game.
"""
import json, os

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

# Location categories (data/locations.json 'kind'), in display order.
CATEGORIES = {
    'chest': {'label': 'Treasure chests', 'default': True, 'experimental': False,
              'note': 'Every chest in the overworld and dungeons.'},
    'scrub': {'label': 'Business Scrubs', 'default': False, 'experimental': True,
              'note': 'Deku Scrubs that sell an item. They can sell major items too.'},
    'skulltula': {'label': 'Gold Skulltulas', 'default': False, 'experimental': True,
                  'note': 'Each one drops a shuffled pick-up instead of its token. Tokens can turn up anywhere.'},
    'pot': {'label': 'Pots, crates, grass & rocks', 'default': False, 'experimental': True,
            'note': 'Only those that always drop the same thing (rupees, hearts, magic, ammo).'},
    'freestanding': {'label': 'Heart Pieces & Containers', 'default': False, 'experimental': True,
                     'note': 'Heart Pieces lying in the world and the Heart Containers left by bosses.'},
}

# Dungeon items: where each kind may end up.
DUNGEON_ITEMS = {
    'small_keys': {'label': 'Small Keys', 'items': {'Item_Dungeon_SmallKey', 'Obj_Dungeon_SmallKey'},
                   'choices': ['vanilla'], 'default': 'vanilla',
                   'locked': {'own_dungeon': 'Needs room-by-room key logic, which is not mapped yet.',
                              'anywhere': 'Keys are generic: one only opens doors in the dungeon it is found in.'}},
    'boss_keys': {'label': 'Boss Keys', 'items': {'Item_Dungeon_BossKey'},
                  'choices': ['vanilla', 'own_dungeon'], 'default': 'vanilla',
                  'locked': {'anywhere': 'A Boss Key only works in the dungeon it is found in.'}},
    'maps_compasses': {'label': 'Maps & Compasses', 'items': {'Item_Dungeon_Map', 'Item_Dungeon_Compass'},
                       'choices': ['vanilla', 'own_dungeon', 'anywhere'], 'default': 'own_dungeon',
                       'locked': {}, 'notes': {'anywhere': 'Outside their own dungeon they show nothing.'}},
}

CHOICE_LABELS = {'vanilla': 'Vanilla', 'own_dungeon': 'Own dungeon', 'anywhere': 'Anywhere'}

# Asked for, but not possible yet; shown in the app so it is clear why.
UNAVAILABLE = {
    'song': {'label': 'Songs', 'note': 'Songs are taught in cutscene scripts, which the randomizer cannot '
                                       'edit yet. They stay with their teachers.'},
}

OTHER = {
    'keep_event_chests': False,    # leave chests that play item-specific scenes vanilla
    'skip_intro': False,           # bypass Navi's wake-up scene; make the narrated opening skippable
    'skippable_cutscenes': False,  # remove the Skip lock from the opening, title and credits
}

# Shown in the app next to the cutscene options.
CUTSCENE_OPTIONS = {
    'skip_intro': {'label': 'Skip the intro',
                   'note': "Navi's wake-up scene is skipped, so you take control right away. The narrated "
                           "opening plays while Kokiri Forest loads, so it can't be cut; it becomes "
                           "skippable with the Skip button instead."},
    'skippable_cutscenes': {'label': 'Every cutscene skippable',
                            'note': 'The game already lets you skip almost every cutscene. This also unlocks '
                                    "the three that normally can't be skipped: the opening, the title and the credits."},
}
AUTO_SKIP_NOTE = ('Of 331 cutscene calls, most are scripted scenes that move Link, load '
                  'areas, hand over items or start fights, and cutting them blindly can leave the screen black '
                  'or break progression. Use the Skip button instead; the option above makes it work everywhere.')

# Logic and world options (randomizer/logic.py milestones, randomizer/world.py flag defaults).
WORLD = {
    'logic': {'label': 'Logic', 'default': 'logic', 'choices': ['logic', 'none'],
              'labels': {'logic': 'Logic', 'none': 'No logic'},
              'notes': {'logic': 'Every seed can be beaten: an item is only placed where you can reach it with the items found before it.',
                        'none': 'Items go anywhere. A seed can be impossible to finish, for example with a key item locked behind itself.'}},
    'open_forest': {'label': 'Open Kokiri Forest', 'default': False,
                    'note': 'The Kokiri boy guarding the exit is gone from the start, so you can leave before the Deku Tree.',
                    'flags': {'KokiriForest_Npc_Kokiri_007_Child_Blocker_00': False}},
    'open_deku': {'label': 'Open Deku Tree', 'default': False,
                  'note': 'Mido stops blocking the Deku Tree, so no sword or shield is needed to go in.',
                  'flags': {'KokiriForest_Npc_Kokiri_Mido_Child_Blocker': False}},
    'open_door': {'label': 'Open Door of Time', 'default': False,
                  'note': 'The Door of Time starts open: you can pull the Master Sword without the Spiritual Stones, Ocarina or Song of Time.',
                  'flags': {'Market_Child_TimeTempleDoor_Opened': True}},
    'open_fountain': {'label': "Open Zora's Fountain", 'default': False,
                      'note': "King Zora has already moved aside, so the way to Zora's Fountain is open without Ruto's Letter.",
                      'flags': {'HavePlayedEvent.Dm_Zora_0010': True}},
}
WORLD_OPEN = [k for k in WORLD if k != 'logic']

# Shop options (randomizer/shops.py).
SHOPS = {
    'shop_items': {'label': 'Shuffle shop stock', 'default': False,
                   'note': 'Consumables, potions and bottled items swap places across every shop. Tunics, '
                           'shields and masks stay put, because the logic counts on buying them there.'},
    'shop_prices': {'label': 'Prices', 'default': 'vanilla', 'choices': ['vanilla', 'random', 'cheap'],
                    'labels': {'vanilla': 'Vanilla', 'random': 'Random', 'cheap': 'Cheap'},
                    'notes': {'vanilla': 'Original prices.',
                              'random': 'Each item costs a quarter to twice its original price (at most 300). '
                                        'Tunics and shields never cost more than usual.',
                              'cheap': 'Everything costs 10 to 60 percent of its original price.'}},
}

# Which item form a location needs (see tools/inventory.py item_forms).
CONTEXT = {'chest': 'get', 'scrub': 'scrub', 'skulltula': 'world', 'pot': 'world', 'freestanding': 'world'}


def defaults():
    d = {'shuffle': [k for k, c in CATEGORIES.items() if c['default']]}
    d.update({k: v['default'] for k, v in DUNGEON_ITEMS.items()})
    d.update(OTHER)
    d.update({k: v['default'] for k, v in SHOPS.items()})
    d.update({k: v['default'] for k, v in WORLD.items()})
    return d


def normalize(s=None):
    """Fill in missing keys and drop invalid values, so old settings files keep working."""
    out = defaults()
    s = dict(s or {})
    if 'shuffle' in s:
        out['shuffle'] = [k for k in CATEGORIES if k in set(s['shuffle'])]
    for k, v in DUNGEON_ITEMS.items():
        if s.get(k) in v['choices']:
            out[k] = s[k]
    for k in OTHER:
        if k in s:
            out[k] = bool(s[k])
    if 'shop_items' in s:
        out['shop_items'] = bool(s['shop_items'])
    if s.get('shop_prices') in SHOPS['shop_prices']['choices']:
        out['shop_prices'] = s['shop_prices']
    if s.get('logic') in WORLD['logic']['choices']:
        out['logic'] = s['logic']
    for k in WORLD_OPEN:
        if k in s:
            out[k] = bool(s[k])
    return out


def summary(s):
    s = normalize(s)
    parts = ['shuffle=' + '+'.join(s['shuffle']) if s['shuffle'] else 'shuffle=none']
    parts += ['%s=%s' % (k, s[k]) for k in DUNGEON_ITEMS]
    parts += ['%s=%s' % (k, s[k]) for k in OTHER]
    parts += ['%s=%s' % (k, s[k]) for k in SHOPS]
    parts += ['%s=%s' % (k, s[k]) for k in WORLD]
    return ', '.join(parts)


_forms = None


def forms():
    global _forms
    if _forms is None:
        _forms = json.load(open(os.path.join(DATA, 'item_forms.json'), encoding='utf-8'))
    return _forms


def actor_for(loc, item):
    """The actor name to write into `loc` for canonical `item`, or None if it cannot go there."""
    f = forms().get(item)
    return f and f[CONTEXT[loc['kind']]]


def fits(loc, item):
    return actor_for(loc, item) is not None


def policy(s, item):
    """'vanilla', 'own_dungeon' or 'anywhere' for dungeon items, else None."""
    for k, v in DUNGEON_ITEMS.items():
        if item in v['items']:
            return s[k]
    return None
