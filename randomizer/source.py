"""Get the game files the randomizer needs straight from a .nup dump.

Only a few dozen files are needed (the maps that hold item locations, the zstd dictionaries
and the resource size table). They are read from the dump, checked against the SHA-256
hashes in data/romfs_manifest.json, and kept in a per-user cache so later runs skip the
dump entirely. The dump itself is only ever opened for reading.
"""
import hashlib, json, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import nup as nupfile

MANIFEST = os.path.join(HERE, '..', 'data', 'romfs_manifest.json')
TITLE_ID = 0x0400486024DEC000


class SourceError(Exception):
    pass


def manifest():
    return json.load(open(MANIFEST, encoding='utf-8'))


def cache_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), '.cache')
    key = hashlib.sha256(json.dumps(manifest()['files'], sort_keys=True).encode()).hexdigest()[:12]
    return os.path.join(base, 'OoTRando', 'romfs-' + key)


def _sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def cached(romfs=None):
    """The cache dir if it holds every manifest file with the right hash, else None."""
    romfs = romfs or cache_dir()
    for rel, sha in manifest()['files'].items():
        p = os.path.join(romfs, rel)
        if not os.path.isfile(p) or _sha(p) != sha:
            return None
    return romfs


def title_ids(n):
    """Title ids listed in the dump's title records (0x40 bytes each, starting at 0xB0)."""
    n.f.seek(0xB0)
    raw = n.f.read(0x80)
    return [struct.unpack_from('<Q', raw, i)[0] for i in (0, 0x40)]


def inspect(nup_path):
    """Open a dump and check it holds the files this randomizer was built against.
    Returns (Nup, {rel: file_entry}); raises SourceError with a readable reason."""
    try:
        n = nupfile.Nup(nup_path)
    except OSError as e:
        raise SourceError('Could not open the file (%s).' % e.strerror)
    except (AssertionError, struct.error, ValueError, IndexError):
        raise SourceError('This is not a .nup dump.')
    ids = title_ids(n)
    if not any(i & ~0xFFF == TITLE_ID for i in ids):
        raise SourceError('This dump is not Ocarina of Time (title ids: %s).'
                          % ', '.join('%016X' % i for i in ids))
    m = manifest()
    prefix = m['prefix']
    want = m['files']
    found = {}
    for p, fe in n.walk():
        if p.startswith(prefix) and p[len(prefix):] in want:
            found[p[len(prefix):]] = fe
    if not found:
        raise SourceError('The dump has no %s update files. The randomizer needs a dump that includes '
                          'the 2.0 update (v131072).' % prefix.split('/')[0])
    missing = sorted(set(want) - set(found))
    if missing:
        raise SourceError('The dump is missing %d needed files, e.g. %s.' % (len(missing), missing[0]))
    wrong = [r for r, fe in found.items() if fe[5].hex() != want[r]]
    if wrong:
        raise SourceError('%d files differ from the 2.0 game this randomizer supports (e.g. %s). '
                          'A different game version?' % (len(wrong), wrong[0]))
    return n, found


def prepare(nup_path=None, log=print):
    """Return a romfs directory holding every needed file, extracting from the dump if needed."""
    have = cached()
    if have:
        log('Using cached game files (%s).' % have)
        return have
    if not nup_path:
        raise SourceError('Select your Ocarina of Time .nup dump first.')
    log('Reading game files from %s ...' % os.path.basename(nup_path))
    n, found = inspect(nup_path)
    dst_root = cache_dir()
    want = manifest()['files']
    for rel, fe in sorted(found.items()):
        data = n.read(fe)
        if hashlib.sha256(data).hexdigest() != want[rel]:
            raise SourceError('%s in the dump is damaged (hash mismatch).' % rel)
        dst = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + '.tmp'
        open(tmp, 'wb').write(data)
        os.replace(tmp, dst)
    n.f.close()
    log('Extracted and verified %d files into %s.' % (len(found), dst_root))
    # drop caches made for older file lists
    parent = os.path.dirname(dst_root)
    key = os.path.basename(dst_root)[len('romfs-'):]
    for d in os.listdir(parent):
        if d.startswith(('romfs-', 'icons-')) and not d.endswith(key):
            shutil.rmtree(os.path.join(parent, d), ignore_errors=True)
    return dst_root
