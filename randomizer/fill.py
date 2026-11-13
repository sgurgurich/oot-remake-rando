"""Seeded item placement (assumed fill) and a playthrough check.

Placement works on canonical item names (each location's vanilla actor). Whether an item
can sit in a location is decided by `fits(loc, item)` (see randomizer/settings.py): the
game has no pick-up version of most equipment, so e.g. the Hookshot can go in a chest or
a scrub but not in a pot.
"""
import random
from . import logic


class FillError(Exception):
    pass


def reachable(state, locs, rules, placed):
    """Sweep: repeatedly collect items at reachable filled locations. Returns reachable ids."""
    seen = set()
    changed = True
    while changed:
        changed = False
        for l in locs:
            i = l['id']
            if i in seen or not rules[i](state): continue
            seen.add(i)
            if i in placed:
                state.add(placed[i]); changed = True
    return seen


def assumed_fill(rng, locs, rules, prog_items, placed, fits):
    """Place each progression item somewhere reachable assuming the player already has
    every progression item not yet placed. Standard technique; guarantees beatability
    under the rules as long as it succeeds."""
    pool = list(prog_items)
    rng.shuffle(pool)
    empty = [l for l in locs if l['id'] not in placed]
    while pool:
        item = pool.pop()
        state = logic.State(pool)
        reach = reachable(state, locs, rules, placed)
        options = [l for l in empty if l['id'] in reach and fits(l, item)]
        if not options:
            raise FillError('no reachable location left for %s' % item)
        spot = rng.choice(options)
        placed[spot['id']] = item
        empty.remove(spot)


def place_restricted(rng, locs, items, placed, allowed):
    """items: [(item, home_loc)]; allowed(loc, item, home) says where each may go."""
    for item, home in items:
        options = [l for l in locs if l['id'] not in placed and allowed(l, item, home)]
        if not options:
            raise FillError('no room for %s in %s' % (item, home['area']))
        placed[rng.choice(options)['id']] = item


def place_junk(rng, locs, junk, placed, fits):
    """Fill the remaining locations; the least flexible items go first."""
    empty = [l for l in locs if l['id'] not in placed]
    rng.shuffle(junk)
    flex = {}
    for item in set(junk):
        flex[item] = sum(1 for l in empty if fits(l, item))
    for item in sorted(junk, key=lambda x: flex[x]):
        options = [l for l in empty if fits(l, item)]
        if not options:
            raise FillError('no location can hold %s' % item)
        spot = rng.choice(options)
        placed[spot['id']] = item
        empty.remove(spot)


def playthrough(locs, rules, placed):
    """Spheres of progression from an empty file: list of [(loc_id, item), ...]."""
    state = logic.State()
    got = set()
    spheres = []
    while True:
        sphere = [l['id'] for l in locs if l['id'] not in got and rules[l['id']](state)]
        if not sphere: break
        got.update(sphere)
        found = [(i, placed[i]) for i in sphere if placed.get(i) in logic.PROGRESSION]
        for _, item in found: state.add(item)
        if found: spheres.append(found)
    return spheres, state, got


def randomize(locs, rules, seed, fixed=(), restricted=(), fits=lambda l, i: True,
              allowed=lambda l, i, home: l['area'] == home['area']):
    """locs: shuffled locations. fixed: ids that keep their vanilla item. restricted: ids
    whose vanilla item must stay near home (allowed(loc, item, home_loc)).
    Returns ({loc_id: item} for every location in locs, spheres)."""
    rng = random.Random(seed)
    base = {l['id']: l['vanilla'] for l in locs if l['id'] in fixed}
    # iterate in location order, never set order: seeds must give the same game in every run
    bound = [(l['vanilla'], l) for l in locs if l['id'] in restricted and l['id'] not in base]
    free = [l for l in locs if l['id'] not in base and l['id'] not in restricted]
    pool = [l['vanilla'] for l in free]
    prog = [x for x in pool if x in logic.PROGRESSION]
    junk = [x for x in pool if x not in logic.PROGRESSION]
    for attempt in range(50):
        trial = dict(base)
        try:
            place_restricted(rng, locs, bound, trial, allowed)
            assumed_fill(rng, locs, rules, prog, trial, fits)
            place_junk(rng, locs, list(junk), trial, fits)
        except FillError:
            continue
        spheres, state, _ = playthrough(locs, rules, trial)
        if state.ev['win']:
            return trial, spheres
    raise FillError('could not build a beatable seed in 50 attempts')
