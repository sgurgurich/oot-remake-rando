"""Cutscene options: skip the intro, make every cutscene skippable.

The edits come from data/cutscene_skips.json (built by tools/cutscene_skips.py, which
explains them). Event flows are only edited in place (u16 event links), so their size never
changes; component lists only lose a key, so they only shrink. Neither needs a new entry
in the resource size table.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import zstandard
import zs, byml, evfl

DATA = os.path.join(HERE, '..', 'data', 'cutscene_skips.json')


def edits():
    return json.load(open(DATA, encoding='utf-8'))


def needed_files():
    """Game files these options read (for data/romfs_manifest.json)."""
    e = edits()
    return sorted(set(e['intro']) | set(e['unlock']))


def _apply_flow_ops(data, ops):
    f = evfl.Flow(data)
    for op in ops:
        kind = op[0]
        if kind == 'next':
            _, i, old, new = op
            assert f.events[i]['next'] == old, ('unexpected flow', op)
            f.set_next(i, new)
        elif kind == 'case':
            _, i, k, old, new = op
            assert f.events[i]['cases'][k][1] == old, ('unexpected flow', op)
            f.set_case(i, k, new)
        elif kind == 'entry':
            _, name, old, new = op
            assert f.entries[name]['main'] == old, ('unexpected flow', op)
            f.set_entry(name, new)
        else:
            raise ValueError(op)
    out = f.bytes()
    assert len(out) == len(data)
    evfl.Flow(out)  # still parses
    return out


def _unlock(data):
    b = byml.Byml(data)
    root = b.root
    root['Components'].pop('SkipSetting')
    out = byml.dump(root, version=b.version)
    assert len(out) <= len(data)
    return out


def files(rom, settings):
    """{romfs path: new file bytes} for the cutscene options switched on in settings."""
    e = edits()
    out = {}
    if settings.get('skip_intro'):
        for rel, ops in e['intro'].items():
            path = os.path.join(rom, rel)
            data = _apply_flow_ops(zs.decompress(rom, path), ops)
            d = zs.pick_dict(rom, path)
            blob = zstandard.ZstdCompressor(level=19, dict_data=d, write_checksum=False).compress(data)
            assert zstandard.ZstdDecompressor(dict_data=d).decompress(blob) == data
            out[rel] = blob
    unlock = list(e['unlock']) if settings.get('skippable_cutscenes') else \
        list(e['intro_unlock']) if settings.get('skip_intro') else []
    for rel in unlock:
        out[rel] = _unlock(open(os.path.join(rom, rel), 'rb').read())
    return out


def write(rom, out_dir, settings):
    """Write the changed files under out_dir/romfs; returns their romfs paths."""
    done = []
    for rel, blob in sorted(files(rom, settings).items()):
        dst = os.path.join(out_dir, 'romfs', rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(blob)
        done.append(rel)
    return done
