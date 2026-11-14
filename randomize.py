"""Generate a randomized romfs mod and spoiler log.

    py randomize.py --seed 1234
    py randomize.py --seed 1234 --shuffle chest,skulltula,pot --boss-keys own_dungeon
    py randomize.py --seed 1234 --keep-event-chests   # leave chests with scripted events vanilla
    py randomize.py --seed 1234 --spoiler-only        # no mod files, just the log
    py randomize.py --nup "path/to/dump.nup"          # read game files from the dump
    py randomize.py --seed 1234 --zip                 # also pack the mod into a .zip
    py randomize.py --nup dump.nup --make-nup --no-folder   # a patched copy of the whole dump

Game files come from --nup (cached after the first run) or from work/raw (see README).
"""
import argparse, datetime, json, os, re, shutil, sys, time, random, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
from randomizer import logic, fill, names, settings as cfg

VERSION = '0.8.3'


def load_locations(kinds=None):
    """Shuffleable locations of the given kinds (default: every kind)."""
    locs = json.load(open(os.path.join(HERE, 'data', 'locations.json'), encoding='utf-8'))
    return [l for l in locs if 'exclude' not in l and (kinds is None or l['kind'] in kinds)]


def scripted(l):
    # Navi-chat-off is harmless; every other chest event may play item-specific scenes.
    return l['kind'] == 'chest' and l.get('event') and l['event'] != 'KokiriForest_TreasureBox_NaviChatOff'


def build(seed, settings=None):
    """Place items for one seed. Returns (locs, placed, spheres, descs, fixed, settings)."""
    s = cfg.normalize(settings)
    logic.configure(s)
    locs = load_locations()  # all of them: unshuffled kinds stay put but still count for logic
    rules, descs = {}, {}
    for l in locs:
        descs[l['id']], rules[l['id']] = logic.rule_for(l)
        if s['logic'] == 'none':
            descs[l['id']], rules[l['id']] = 'none (no logic)', (lambda st: True)
    fixed, restricted = set(), set()
    for l in locs:
        pol = cfg.policy(s, l['vanilla'])
        if l['kind'] not in s['shuffle'] or pol == 'vanilla' or (s['keep_event_chests'] and scripted(l)):
            fixed.add(l['id'])
        elif pol == 'own_dungeon':
            restricted.add(l['id'])

    def allowed(loc, item, home):  # own dungeon: a chest in the same area
        return loc['area'] == home['area'] and loc['kind'] == 'chest' and cfg.fits(loc, item)
    placed, spheres = fill.randomize(locs, rules, seed, fixed, restricted, cfg.fits, allowed)
    return locs, placed, spheres, descs, fixed, s


def spoiler(seed, settings, locs, placed, spheres, descs):
    loc_name = names.location_names(locs)
    shown = [l for l in locs if l['kind'] in settings['shuffle']]
    item = names.item_names()
    by_id = {l['id']: l for l in locs}
    out = ['OoT Remake Randomizer %s' % VERSION, 'Seed: %s' % seed,
           'Settings: %s' % cfg.summary(settings), '',
           *(['NO LOGIC: items were placed anywhere; this seed may be impossible to finish.', ''] if settings.get('logic') == 'none' else []),
           'Playthrough (one way to collect every progression item; spheres are in logic order):']
    for n, sphere in enumerate(spheres, 1):
        out.append('  Sphere %d' % n)
        for i, it in sorted(sphere, key=lambda x: loc_name[x[0]]):
            out.append('    %-70s %s' % (loc_name[i], item.get(it, it)))
    out += ['', 'All shuffled locations:']
    for l in sorted(shown, key=lambda l: loc_name[l['id']]):
        i = l['id']; it = placed[i]
        mark = '' if it != l['vanilla'] else '  (vanilla)'
        out.append('  %-70s %s%s' % (loc_name[i], item.get(it, it), mark))
    from randomizer import shops
    stock, new_prices = shops.stock(seed, settings), shops.prices(seed, settings)
    if stock or new_prices:
        d = shops.data()
        price = lambda a: new_prices.get(a, d['prices'].get(a, {}).get('price'))
        out += ['', 'Shops (slot: item, price):']
        for s in sorted(d['slots'], key=lambda s: (s['shop'], ','.join(s['ages']), s['index'], s['id'])):
            a = stock.get(s['id'], s['vanilla'])
            out.append('  %-44s %-34s %s' % ('%s (%s) slot %d' % (s['shop'], '/'.join(s['ages']), s['index']),
                                             d['names'].get(a, a), price(a)))
    out += ['', 'Logic rule per location (conservative, see randomizer/logic.py):']
    for l in sorted(shown, key=lambda l: loc_name[l['id']]):
        out.append('  %-70s %s' % (loc_name[l['id']], descs[l['id']]))
    return '\n'.join(out) + '\n'


def random_seed():
    return str(random.SystemRandom().randrange(10 ** 9))


DEFAULT_TITLE = 'OoT Remake Rando - {date}'


def game_title(template, seed):
    """Fill in {date} (today, YYYY-MM-DD) and {seed} in the game name template."""
    t = (template or '').strip()
    return t.replace('{date}', datetime.date.today().isoformat()).replace('{seed}', str(seed)) if t else None


def safe_name(seed):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(seed)).strip('._') or 'seed'


def generate(seed=None, out=None, settings=None, nup=None, rom=None, write_mod=True,
             write_spoiler=True, make_zip=False, overwrite=False, log=print,
             make_nup=False, make_folder=True, progress=None, nup_title=DEFAULT_TITLE):
    """Build one seed. Game files come from `rom` (a romfs dir), else from `nup` (via the
    cache), else from work/raw. Outputs (any combination):
      make_folder  out/OoTRando-<seed>/romfs/...   (romfs mod)
      make_zip     out/OoTRando-<seed>.zip         (the same folder, zipped)
      make_nup     out/OoTRando-<seed>.nup         (a full copy of the dump with the changes applied;
                                                    the original dump is only read)
    progress(done, total) reports the .nup copy. nup_title is the game name emulators show for
    the patched .nup ({date} and {seed} are filled in; empty keeps the original name).
    Returns a dict describing what was written."""
    import patcher, nup_patch
    from randomizer import source
    seed = str(seed) if seed not in (None, '') else random_seed()
    out = os.path.normpath(out or os.path.join(HERE, 'out'))
    name = 'OoTRando-' + safe_name(seed)
    mod_dir = os.path.join(out, name)
    zip_path = mod_dir + '.zip'
    nup_path = mod_dir + '.nup'
    log_path = os.path.join(out, name + '-spoiler.txt')
    make_zip = make_zip and write_mod
    make_nup = make_nup and write_mod
    make_folder = make_folder and write_mod
    if write_mod:
        if make_nup:
            if not nup or not os.path.isfile(nup):
                raise source.SourceError('A patched .nup is built from your original dump: select it first.')
            if nup_patch.same_file(nup, nup_path):
                raise source.SourceError('The output folder holds the original dump under the same name; pick another folder.')
            source.inspect(nup)[0].f.close()  # the right game and version, before any work
        if rom is None:
            rom = source.prepare(nup, log) if (nup or source.cached()) else patcher.ROM
        targets = [p for p, on in ((mod_dir, make_folder), (zip_path, make_zip), (nup_path, make_nup)) if on]
        clash = [p for p in targets if os.path.exists(p)]
        if clash and not overwrite:
            raise FileExistsError('%s already exists' % clash[0])

    t0 = time.time()
    locs, placed, spheres, descs, fixed, settings = build(seed, settings)
    moved = sum(1 for l in locs if placed[l['id']] != l['vanilla'])
    shuffled = sum(1 for l in locs if l['kind'] in settings['shuffle'])
    log('Seed %s: %d locations shuffled, %d changed, %d progression spheres (%.1fs).'
        % (seed, shuffled, moved, len(spheres), time.time() - t0))
    os.makedirs(out, exist_ok=True)
    result = {'seed': seed, 'mod_dir': None, 'zip': None, 'nup': None, 'spoiler': None, 'out': out}
    if write_spoiler:
        open(log_path, 'w', encoding='utf-8').write(spoiler(seed, settings, locs, placed, spheres, descs))
        result['spoiler'] = log_path
        log('Spoiler log: %s' % log_path)
    if not write_mod:
        return result

    plan = {l['id']: cfg.actor_for(l, placed[l['id']]) for l in locs if placed[l['id']] != l['vanilla']}
    from randomizer import shops
    shop_stock = shops.stock(seed, settings)
    plan.update(shop_stock)
    work = mod_dir if make_folder else os.path.join(out, '.%s.work' % name)
    for p in (work, mod_dir if make_folder else None):
        if p and os.path.exists(p):
            shutil.rmtree(p)
    log('Patching maps ...')
    try:
        files = patcher.apply(plan, work, rom=rom, log=lambda *_: None) if plan else []
        from randomizer import skips
        extra = skips.write(rom, work, settings)
        if extra:
            log('Cutscene options: %d files changed.' % len(extra))
        from randomizer import world
        opened = world.write(rom, work, settings)
        if opened:
            log('World options: %s.' % ', '.join(cfg.WORLD[k]['label'] for k in cfg.WORLD_OPEN if settings.get(k)))
        extra += opened
        priced, new_prices = shops.write(rom, work, seed, settings)
        if shop_stock or priced:
            log('Shops: %d shelf slots restocked, %d prices changed.' % (len(shop_stock), len(new_prices)))
        extra += priced
        files = sorted(set(files) | set(extra))
        log('Patched %d game files.' % len(files))
        if make_folder:
            result['mod_dir'] = mod_dir
            log('Mod folder: %s' % mod_dir)
        if make_zip:
            tmp = zip_path + '.tmp'
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z:  # .zs files are already compressed
                for f in files:
                    z.write(os.path.join(work, 'romfs', f), '/'.join((name, 'romfs', f)))
            os.replace(tmp, zip_path)
            result['zip'] = zip_path
            log('Zip: %s' % zip_path)
        if make_nup:
            if os.path.exists(nup_path):
                os.remove(nup_path)  # only reached with overwrite; never the original (checked above)
            nup_patch.write_patched(nup, nup_path, nup_patch.mod_replacements(work, source.manifest()['prefix']),
                                    progress=progress, log=log, title=game_title(nup_title, seed))
            result['nup'] = nup_path
            log('Patched dump: %s' % nup_path)
    finally:
        if not make_folder and os.path.exists(work):
            shutil.rmtree(work, ignore_errors=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--seed', default=None, help='any text or number; random if omitted')
    ap.add_argument('--out', default=os.path.join(HERE, 'out'))
    ap.add_argument('--nup', default=None, help='your .nup dump (only needed until the files are cached)')
    ap.add_argument('--shuffle', default=','.join(cfg.defaults()['shuffle']),
                    help='comma-separated location kinds: %s' % ','.join(cfg.CATEGORIES))
    for k, v in cfg.DUNGEON_ITEMS.items():
        ap.add_argument('--' + k.replace('_', '-'), choices=v['choices'], default=v['default'])
    ap.add_argument('--keep-event-chests', action='store_true',
                    help='leave chests that trigger scripted events (Bow, Hammer, Slingshot, ...) vanilla')
    ap.add_argument('--skip-intro', action='store_true', help="skip Navi's wake-up scene; opening becomes skippable")
    ap.add_argument('--no-logic', action='store_true', help='place items anywhere (seeds may be unbeatable)')
    for k in cfg.WORLD_OPEN:
        ap.add_argument('--' + k.replace('_', '-'), action='store_true', help=cfg.WORLD[k]['note'])
    ap.add_argument('--shop-items', action='store_true', help='shuffle shop stock (consumables)')
    ap.add_argument('--shop-prices', choices=list(cfg.SHOPS['shop_prices']['choices']), default='vanilla')
    ap.add_argument('--skippable-cutscenes', action='store_true',
                    help='unlock the Skip button on the opening, title and credits')
    ap.add_argument('--spoiler-only', action='store_true')
    ap.add_argument('--no-spoiler', action='store_true')
    ap.add_argument('--zip', action='store_true', help='also write OoTRando-<seed>.zip')
    ap.add_argument('--make-nup', action='store_true',
                    help='also write OoTRando-<seed>.nup, a patched copy of --nup (needs ~26 GB free)')
    ap.add_argument('--no-folder', action='store_true', help='skip the OoTRando-<seed>/ romfs folder')
    ap.add_argument('--nup-title', default=DEFAULT_TITLE,
                    help='game name shown by emulators for the patched .nup; {date} and {seed} are filled in; '
                         'empty keeps the original (default: %(default)s)')
    ap.add_argument('--overwrite', action='store_true')
    a = ap.parse_args()
    try:
        st = {'shuffle': [k for k in a.shuffle.split(',') if k], 'keep_event_chests': a.keep_event_chests,
              'skip_intro': a.skip_intro, 'skippable_cutscenes': a.skippable_cutscenes,
              'shop_items': a.shop_items, 'shop_prices': a.shop_prices,
              'logic': 'none' if a.no_logic else 'logic'}
        st.update({k: getattr(a, k) for k in cfg.WORLD_OPEN})
        st.update({k: getattr(a, k) for k in cfg.DUNGEON_ITEMS})
        bad = set(st['shuffle']) - set(cfg.CATEGORIES)
        if bad: raise SystemExit('unknown --shuffle kinds: %s' % ', '.join(sorted(bad)))
        last = [-1]
        def prog(done, total):
            pct = int(done * 100 / max(total, 1))
            if pct != last[0] and pct % 10 == 0:
                last[0] = pct; print('  copying dump: %d%%' % pct)
        generate(a.seed, a.out, st, nup=a.nup, write_mod=not a.spoiler_only,
                 write_spoiler=not a.no_spoiler, make_zip=a.zip, overwrite=a.overwrite,
                 make_nup=a.make_nup, make_folder=not a.no_folder, progress=prog, nup_title=a.nup_title)
    except FileExistsError as e:
        raise SystemExit('%s; pass --overwrite or pick another seed' % e)


if __name__ == '__main__':
    main()
