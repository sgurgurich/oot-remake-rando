"""Conservative logic for chest shuffle.

Every rule is a deliberate *over*-approximation built from the original game's
progression: a check is only treated as reachable once the player holds every item
that could plausibly be needed for it (in practice, everything needed to clear the
whole dungeon or reach the whole area). Over-requiring is always safe: it can make
seeds less varied, but it cannot produce a seed that is impossible to beat.

None of this has been checked against the remake yet. The remake may move or change
requirements; when a rule is confirmed in game it can be tightened, and when the remake
needs something the original did not, it must be added here.

What stays vanilla (not shuffled) and is therefore assumed to be where the original
game has it: songs, Ocarina, bottles, scales, tunics, magic, Master Sword, Spiritual
Stones and Medallions (boss rewards), Light Arrows, NPC and shop items, and all Small
Keys and Boss Keys (they stay in their original chests, so key logic is not needed).
Deku Shields are assumed purchasable whenever needed.
"""

# Progression items, by the actor name chests use to spawn them.
SWORD = 'Item_Sword_Kokiri'
SLING = 'Item_Range_SlingShot'
BOOM = 'Item_Boomerang'
BOMBS = 'Item_BombBag_Small'
BOW = 'Item_Range_Bow'
HOOK = 'Item_Hookshot'
LONG = 'Item_Longshot'
HAMMER = 'Item_Hammer'
LENS = 'Item_GlassTruth'
SILVER = 'Item_Gauntlet_Silver'
GOLD = 'Item_Gauntlet_Gold'
MIRROR = 'Item_Shield_Mirror'
IRON = 'Item_HeavyBoot'
HOVER = 'Item_HoverBoot'

PROGRESSION = [SWORD, SLING, BOOM, BOMBS, BOW, HOOK, LONG, HAMMER, LENS, SILVER, GOLD, MIRROR, IRON, HOVER]

# Items that keep their original chest in every seed.
VANILLA_ITEMS = {'Item_Dungeon_SmallKey', 'Item_Dungeon_BossKey'}

CHILD_KIT = (SWORD, SLING, BOOM, BOMBS)
ADULT_KIT = (BOW, HOOK, LONG, HAMMER, BOMBS, LENS, SILVER, IRON, HOVER)

# Each milestone: (milestones it needs first, items needed to fully clear it).
# Order matters: a milestone may only depend on ones listed above it.
BASE_MILESTONES = [
    ('deku', (), (SWORD, SLING)),                                   # Kokiri's Emerald
    ('out', ('deku',), ()),                                         # Kokiri Forest exit opens after the Deku Tree
    ('dodongo', ('out',), (BOMBS, SWORD, SLING)),                   # Goron's Ruby
    ('jabu', ('out',), (BOMBS, SWORD, SLING, BOOM)),                # Zora's Sapphire (Ruto's Letter is vanilla)
    ('adult', ('deku', 'dodongo', 'jabu'), ()),                     # Ocarina of Time, Master Sword
    ('forest', ('adult',), (HOOK, BOW)),
    ('fire', ('adult',), (HOOK, HAMMER, BOMBS, BOW)),
    ('ice', ('adult',), (BOMBS, BOW, HOOK)),                        # Zora's Fountain opens after Jabu-Jabu
    ('water', ('adult',), (IRON, HOOK, LONG, BOW)),
    ('well', ('adult',), (LENS, SWORD, BOMBS)),                     # Song of Storms is learned as adult
    ('shadow', ('forest', 'fire', 'water'), (LENS, HOVER, HOOK, BOMBS, BOW)),
    ('spirit_reach', ('adult',), (LENS, HOOK, LONG, BOW, BOMBS)),   # Gerudo card, Wasteland, Requiem
    ('spirit', ('spirit_reach',), (SLING, BOOM, SILVER, MIRROR)),
    ('gtg', ('spirit_reach',), (HAMMER, SILVER, IRON, HOVER)),
    ('light_arrows', ('shadow', 'spirit'), ()),
    ('ganon', ('forest', 'fire', 'water', 'shadow', 'spirit', 'light_arrows'), ADULT_KIT + (MIRROR,)),
    ('child_ow', ('out', 'adult'), CHILD_KIT),                      # adult: some child spots need Song of Storms
    ('adult_ow', ('adult',), ADULT_KIT),
    ('win', ('ganon',), (GOLD,)),
]


def milestones(opts=None):
    """The milestone table for the world options (randomizer/settings.py WORLD):
      open_deku      Mido no longer blocks the Deku Tree: entering needs no sword, and Gohma
                     can be beaten with Deku Sticks (always buyable), so only the Slingshot.
      open_forest    the Kokiri Forest exit is open from the start: leaving needs no Deku Tree.
      open_door      the Door of Time is open: becoming adult only needs reaching the Temple of
                     Time, not the three Spiritual Stones.
      open_fountain  King Zora has already moved: adult Zora's Fountain (Ice Cavern) no longer
                     waits for the child-era Zora's Domain story (approximated by Jabu-Jabu).
    """
    opts = opts or {}
    out = []
    for name, pre, items in BASE_MILESTONES:
        if name == 'deku' and opts.get('open_deku'):
            items = (SLING,)
        elif name == 'out' and opts.get('open_forest'):
            pre = ()
        elif name == 'adult' and opts.get('open_door'):
            pre = ('out',)
        elif name == 'ice':
            pre = ('adult',) if opts.get('open_fountain') else ('adult', 'jabu')
        out.append((name, pre, items))
    return out


MILESTONES = milestones()
SPEC = {name: (pre, items) for name, pre, items in MILESTONES}


def configure(opts):
    """Switch the module to the milestone table for these settings (call before building)."""
    global MILESTONES, SPEC
    MILESTONES = milestones(opts)
    SPEC = {name: (pre, items) for name, pre, items in MILESTONES}


class State:
    def __init__(self, items=()):
        self.items = set(items)
        self.ev = {}
        self.update()

    def has(self, *names):
        return all(n in self.items for n in names)

    def add(self, item):
        if item not in self.items:
            self.items.add(item)
            self.update()

    def update(self):
        e = {}
        for name, pre, items in MILESTONES:
            e[name] = all(e[p] for p in pre) and self.has(*items)
        self.ev = e


DUNGEON_RULE = {
    'InsideTheDekuTree': 'deku', 'DodongoCavern': 'dodongo', 'InsideJabuJabuBelly': 'jabu',
    'ForestTemple': 'forest', 'FireTemple': 'fire', 'WaterTemple': 'water', 'IceCavern': 'ice',
    'BottomOfTheWell': 'well', 'ShadowTemple': 'shadow', 'SpiritTemple': 'spirit',
    'GerudoTrainingGround': 'gtg', 'InsideGanonCastle': 'ganon',
}


def _rule(pre, items, vanilla):
    """Predicate: milestones `pre` done and `items` held, except the location's own vanilla
    item. The original game gives that item at this very spot, so it is never needed to
    reach it; dropping it is what lets e.g. the Slingshot stay in the Deku Tree."""
    items = tuple(i for i in items if i != vanilla)
    desc = ' + '.join(list(pre) + [i.replace('Item_', '') for i in items]) or 'none'
    return desc, lambda s: all(s.ev[p] for p in pre) and s.has(*items)


def _milestone(name, vanilla, extra=()):
    pre, items = SPEC[name]
    return _rule(pre, tuple(items) + tuple(extra), vanilla)


def rule_for(loc):
    """Return (description, predicate(State)) for a location dict from data/locations.json."""
    area, vanilla, event = loc['area'], loc['vanilla'], loc.get('event')

    # Identified individually: Mido's House (4 chests next to Link's house) and the
    # Kokiri Sword chest are open to a new child save.
    if area == 'KokiriForest' and event in ('KokiriForest_TreasureBox_NaviChatOff', 'Get_StoneOfForest_GetSword'):
        return _rule((), (), vanilla)

    if area == 'InsideGanonCastle' and vanilla != GOLD:
        return _milestone('ganon', vanilla, (GOLD,))
    if area in DUNGEON_RULE:
        return _milestone(DUNGEON_RULE[area], vanilla)

    # Spirit Temple's hands on the Desert Colossus.
    if area == 'DesertColossus':
        if vanilla == SILVER:  # child-side hand
            return _rule(('spirit_reach',), (SLING, BOOM), vanilla)
        if vanilla == MIRROR:  # adult-side hand
            return _rule(('spirit_reach',), (SLING, BOOM, SILVER), vanilla)
        return _rule(('spirit', 'child_ow', 'adult_ow'), (), vanilla)

    # Dampé's race (Graveyard, adult): the race needs no items in the original.
    if event == 'MiniGame_DampeRace_OpenGoalTBox' and vanilla == HOOK:
        return _rule(('adult',), (), vanilla)

    # Any other overworld chest: unidentified, so require the full kit for every age it exists in.
    ages = set(loc['ages'])
    pre, items = [], []
    if 'child' in ages or 'any' in ages:
        pre += list(SPEC['child_ow'][0]); items += CHILD_KIT
    if 'adult' in ages or 'any' in ages:
        pre += list(SPEC['adult_ow'][0]); items += ADULT_KIT
    return _rule(tuple(dict.fromkeys(pre)), tuple(dict.fromkeys(items)), vanilla)
