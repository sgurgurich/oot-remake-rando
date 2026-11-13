"""Generate many seeds under several settings and check each one independently of the fill code.

    py tests/test_seeds.py [count]
"""
import os, sys, collections, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import randomize
from randomizer import logic, settings as cfg

PRESETS = {
    'default': {},
    'events kept': {'keep_event_chests': True},
    'everything': {'shuffle': list(cfg.CATEGORIES), 'boss_keys': 'own_dungeon', 'maps_compasses': 'anywhere'},
    'everything, events kept': {'shuffle': list(cfg.CATEGORIES), 'boss_keys': 'own_dungeon',
                                'keep_event_chests': True},
    'no chests': {'shuffle': ['skulltula', 'pot', 'freestanding'], 'maps_compasses': 'vanilla'},
    'open world': {'shuffle': list(cfg.CATEGORIES), 'open_forest': True, 'open_deku': True, 'open_door': True,
                   'open_fountain': True, 'boss_keys': 'own_dungeon'},
    'open door only': {'open_door': True},
    'no logic': {'shuffle': list(cfg.CATEGORIES), 'logic': 'none', 'boss_keys': 'own_dungeon'},
}


def check(seed, settings):
    locs, placed, spheres, descs, fixed, s = randomize.build(seed, settings)
    rules = {l['id']: logic.rule_for(l)[1] for l in locs}
    by_id = {l['id']: l for l in locs}
    # 1. same multiset of items as vanilla: nothing created or lost
    assert collections.Counter(placed.values()) == collections.Counter(l['vanilla'] for l in locs), seed
    for l in locs:
        item = placed[l['id']]
        # 2. every item is in a form its location can hold (no Hookshot in a pot)
        assert cfg.actor_for(l, item), (seed, l['kind'], item)
        # 3. dungeon item policies
        pol = cfg.policy(s, l['vanilla'])
        if pol == 'vanilla' or l['id'] in fixed or l['kind'] not in s['shuffle']:
            assert item == l['vanilla'], (seed, l['id'])
        pol = cfg.policy(s, item)
        if pol == 'own_dungeon':
            homes = {x['area'] for x in locs if x['vanilla'] == item}
            assert l['area'] in homes and l['kind'] == 'chest', (seed, item, l['area'])
        if item in logic.PROGRESSION:
            assert l['kind'] in ('chest', 'scrub'), (seed, item, l['kind'])
    # own-dungeon items keep their per-dungeon count
    for k, v in cfg.DUNGEON_ITEMS.items():
        if s[k] == 'own_dungeon':
            want = collections.Counter((l['area'], l['vanilla']) for l in locs if l['vanilla'] in v['items'])
            got = collections.Counter((l['area'], placed[l['id']]) for l in locs if placed[l['id']] in v['items'])
            assert want == got, (seed, k)
    if s['logic'] == 'none':
        return locs, placed  # no reachability promise without logic
    # 4. independent sweep from an empty save reaches the win condition and every location
    state = logic.State(); got = set()
    while True:
        new = [l['id'] for l in locs if l['id'] not in got and rules[l['id']](state)]
        if not new: break
        got.update(new)
        for i in new:
            if placed[i] in logic.PROGRESSION: state.add(placed[i])
    assert state.ev['win'], ('unbeatable', seed)
    assert len(got) == len(locs), ('unreachable locations', seed, len(locs) - len(got))
    return locs, placed


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    t0 = time.time()
    for name, preset in PRESETS.items():
        where = collections.defaultdict(collections.Counter)
        t1 = time.time()
        for i in range(n):
            locs, placed = check('test-%d' % i, preset)
            by = {l['id']: l for l in locs}
            for lid, item in placed.items():
                if item in logic.PROGRESSION: where[item][by[lid]['kind']] += 1
        moved = sum(1 for l in locs if placed[l['id']] != l['vanilla'])
        shuffled = sum(1 for l in locs if l['kind'] in cfg.normalize(preset)['shuffle'])
        print('%-26s %d seeds OK (%.0fs), %d shuffled, e.g. %d changed; progression lands in %s'
              % (name, n, time.time() - t1, shuffled, moved, dict(sum(where.values(), collections.Counter()))))
    print('all presets OK in %.0fs' % (time.time() - t0))
